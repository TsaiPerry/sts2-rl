"""CLI: ``py -m sts2_rl.live.export_onnx <ckpt.pt> --out model.onnx``,
or ``py -m sts2_rl.live.export_onnx --stub --out stub.onnx`` (no checkpoint
needed).

Exports the run-scale policy's masked action logits as a fixed-shape ONNX
graph consumed by the future C# mod's ``OnnxPolicy`` (Task 13): inputs
``f: float32[1, f_dim]``, ``i: int64[1, i_dim]``, ``mask: bool[1, n_actions]``
(``True`` = legal), output ``logits: float32[1, n_actions]`` (masked
positions == ``_MASK_FILL``, -1e8 — the same fill value
``models.py``'s ``action_logits`` implementations already use). Batch is
fixed at 1 (no dynamic axes), opset 17.

``f_dim``/``i_dim``/``n_actions`` are read live from
``sts2_rl.run_env.run_obs_layout()``/``sts2_rl.run_env.N_ACTIONS`` — the same
accessors ``sts2_rl/live/contract.py`` uses — never hardcoded here.

A real checkpoint is loaded via ``sts2_rl.checkpoints.load_agent`` (env_kind
``"run"``), which refuses anything off today's ``RUN_OBS_SCHEMA_VERSION`` /
head version / shape (see ``checkpoints.check_checkpoint``) before this
module ever sees it. ``--stub`` instead exports ``_StubModel``: a
parameter-free module whose logits are uniformly 0.0 at every legal position
(useful for standing up the C# side before a trained checkpoint exists).

Both paths run through the same post-export **parity gate**: N random
``(f, i, mask)`` triples are pushed through the torch module (the thing that
was just exported, not a separately-reloaded copy) and the freshly written
ONNX graph via ``onnxruntime``. The run fails — deleting the ``.onnx`` file
and exiting nonzero — unless both hold at every sample: the **argmax over the
legal actions agrees**, and the delta is within ``--gate-rel-tol``
**relative** to that sample's logit scale. A broken export is therefore never
left on disk. See ``parity_gate`` for why the criteria are argmax-and-relative
rather than the absolute ``max|Δ| < 1e-4`` this used to apply.

Dependencies (``py -m pip install onnx onnxruntime``): installed here as
onnx 1.22.0 / onnxruntime 1.28.0, on top of this machine's torch
2.13.0+cu130. Export and the parity gate both run on CPU (``device="cpu"``)
regardless of what training used — the C# consumer runs CPU ONNX Runtime.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys

import numpy as np
import torch

from .. import run_env
from ..checkpoints import load_agent
from ..tensor_obs import TensorObs

#: Same illegal-action fill value every ``models.py`` ``action_logits``
#: implementation already uses (``models._MASK_FILL``) — kept as a local
#: literal rather than importing the private constant, since the stub model
#: (which never touches ``models.py`` at all) needs it too.
_MASK_FILL = -1e8

DEFAULT_GATE_N = 32

#: Parity tolerance, RELATIVE to the logit scale of each sample (see
#: ``parity_gate``). 1e-4 is ~40x looser than what a faithful export of
#: today's models actually measures (~2-3e-6 for v22_s25/v23_s26) while still
#: being orders of magnitude tighter than any real export defect.
DEFAULT_GATE_REL_TOL = 1e-4

#: Floor on the per-sample scale the relative tolerance divides by, so a row of
#: near-zero logits is held to ``DEFAULT_GATE_REL_TOL`` *absolutely* rather than
#: to ``delta / ~0``. Makes the gate a standard mixed abs/rel tolerance.
_SCALE_FLOOR = 1.0


class _StubModel(torch.nn.Module):
    """A checkpoint-free stand-in with the same ``action_logits`` contract as
    the real models: uniform 0.0 logits at every legal position, ``_MASK_FILL``
    everywhere else. No parameters, so nothing to load — ``--stub`` exists so
    the C# side (and this exporter's own plumbing) can be exercised before a
    trained checkpoint exists."""

    def action_logits(self, obs: TensorObs, mask: torch.Tensor) -> torch.Tensor:
        # Genuinely reads `f`/`i` (as opposite-of-noop, zero-weighted terms)
        # rather than only their static `.shape`/`.device` — the tracer used
        # by `torch.onnx.export` records shape/device lookups as constants at
        # trace time, so an implementation that touched only those two would
        # have both inputs pruned from the exported graph entirely (observed:
        # onnxruntime then rejects "f"/"i" as unknown input names). Multiplying
        # each tensor's sum by 0.0 keeps a real data dependency without
        # changing any value.
        zeros = mask.to(torch.float32) * 0.0
        zeros = zeros + obs.f.sum() * 0.0 + obs.i.sum().to(torch.float32) * 0.0
        return zeros.masked_fill(~mask, _MASK_FILL)


class _ExportWrapper(torch.nn.Module):
    """Adapts any ``action_logits(TensorObs, mask) -> logits`` model (the real
    ``EntitySetActorCritic`` or ``_StubModel``) to the flat ``(f, i, mask) ->
    logits`` signature ``torch.onnx.export`` traces."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, f: torch.Tensor, i: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        obs = TensorObs(f=f, i=i)
        return self.model.action_logits(obs, mask)


def _example_inputs(f_dim: int, i_dim: int, n_actions: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    f = torch.from_numpy(rng.random((1, f_dim), dtype=np.float32))
    i = torch.from_numpy(rng.integers(0, 5, (1, i_dim)).astype(np.int64))
    mask = torch.zeros((1, n_actions), dtype=torch.bool)
    mask[0, 0] = True
    return f, i, mask


def _random_batch(rng: np.random.Generator, f_dim: int, i_dim: int, n_actions: int):
    """One ``(f, i, mask)`` triple as numpy arrays, matching the graph's
    declared dtypes — used by both the parity gate and its test."""
    f = rng.random((1, f_dim), dtype=np.float32)
    i = rng.integers(0, 5, (1, i_dim)).astype(np.int64)
    mask = rng.random((1, n_actions)) < 0.3
    if not mask.any():
        mask[0, 0] = True  # avoid an all-illegal mask, never a real state
    return f, i, mask


@dataclasses.dataclass(frozen=True)
class ParityResult:
    """What the parity gate measured, and whether that passes.

    ``max_abs`` is reported but deliberately NOT a gate criterion: it scales
    with the model's logit magnitudes and input density, neither of which says
    anything about export faithfulness. See ``parity_gate``.
    """

    n: int
    max_abs: float
    max_rel: float
    argmax_mismatches: int
    min_margin: float
    rel_tol: float

    @property
    def passed(self) -> bool:
        return self.argmax_mismatches == 0 and self.max_rel < self.rel_tol

    def describe(self) -> str:
        verdict = "OK" if self.passed else "FAILED"
        reasons = []
        if self.argmax_mismatches:
            reasons.append(
                f"{self.argmax_mismatches}/{self.n} samples chose a different "
                f"argmax over legal actions")
        if self.max_rel >= self.rel_tol:
            reasons.append(
                f"max relative delta {self.max_rel:.3e} >= tolerance {self.rel_tol:.1e}")
        detail = f" — {'; '.join(reasons)}" if reasons else ""
        return (
            f"parity gate {verdict}{detail} "
            f"[{self.n} samples: argmax {self.n - self.argmax_mismatches}/{self.n} agree, "
            f"max|Δ|={self.max_abs:.3e}, max relative Δ={self.max_rel:.3e}, "
            f"min top1-top2 margin={self.min_margin:.4f}]")


def parity_gate(
    wrapper: torch.nn.Module,
    onnx_path_or_session,
    f_dim: int,
    i_dim: int,
    n_actions: int,
    n: int = DEFAULT_GATE_N,
    rel_tol: float = DEFAULT_GATE_REL_TOL,
    _mask_override: "np.ndarray | None" = None,
) -> ParityResult:
    """Push ``n`` random ``(f, i, mask)`` triples through ``wrapper`` (torch)
    and the exported graph (onnxruntime), and measure whether the two agree.

    The gate's criteria are **argmax agreement over the legal actions** and a
    **relative** delta tolerance — not an absolute one. Rationale, from the
    2026-08-25 v23 export:

    * What actually matters downstream is which action the C# ``OnnxPolicy``
      picks, so the argmax is checked directly rather than inferred from a
      proxy. An export that reorders the top of the distribution fails here
      even if every individual delta is tiny.
    * An absolute tolerance measures float32 accumulation noise in a dense
      ``f_dim``-wide matmul, which grows with model width and input density.
      The previous absolute ``1e-4`` tripped on v23_s26 (hidden 1024) at
      1.03e-4 — while v22_s25, already deployed and fine, measures 1.755e-4
      over 512 samples and had only passed because a 32-sample draw missed the
      tail. Neither was an export defect; the threshold was tracking model
      size. Relative to the ~|90| logit scale both sit at ~3e-6.
    * Real export defects (inputs pruned from the graph, wrong opset
      semantics, control flow baked in at trace time) miss by whole orders of
      magnitude, so they trip any of these tolerances.

    An argmax difference is only counted when the two candidates are further
    apart than the tolerance in the torch logits: if the model rates two legal
    actions as indistinguishable, which one wins is arbitrary and a flip is not
    a parity failure.

    Masked positions are excluded from every metric — they are ``_MASK_FILL``
    on both sides and carry no decision weight.

    Does not raise or delete anything itself; the CLI decides what to do with
    the result, so tests can call this directly. ``onnx_path_or_session``
    accepts a path or an already-constructed session, and ``_mask_override``
    pins the mask, so the decision logic can be tested with canned logits.
    """
    if isinstance(onnx_path_or_session, str):
        import onnxruntime as ort
        sess = ort.InferenceSession(
            onnx_path_or_session, providers=["CPUExecutionProvider"])
    else:
        sess = onnx_path_or_session

    rng = np.random.default_rng(12345)
    wrapper.eval()
    max_abs = 0.0
    max_rel = 0.0
    argmax_mismatches = 0
    min_margin = float("inf")

    with torch.no_grad():
        for _ in range(n):
            f, i, mask = _random_batch(rng, f_dim, i_dim, n_actions)
            if _mask_override is not None:
                mask = _mask_override
            torch_out = wrapper(
                torch.from_numpy(f), torch.from_numpy(i), torch.from_numpy(mask)
            ).numpy()
            (onnx_out,) = sess.run(None, {"f": f, "i": i, "mask": mask})

            legal = mask[0]
            t_legal = torch_out[0][legal]
            delta = float(np.abs(torch_out[0][legal] - onnx_out[0][legal]).max())
            scale = max(float(np.abs(t_legal).max()), _SCALE_FLOOR)
            max_abs = max(max_abs, delta)
            max_rel = max(max_rel, delta / scale)

            # argmax restricted to legal positions, so a masking bug shows up
            # here as a disagreement rather than being hidden by _MASK_FILL
            # happening to be identical on both sides.
            t_pick = int(np.argmax(np.where(legal, torch_out[0], -np.inf)))
            o_pick = int(np.argmax(np.where(legal, onnx_out[0], -np.inf)))
            if t_pick != o_pick:
                # Only a real disagreement if torch itself separates them by
                # more than the tolerance; otherwise it is a tie-break flip.
                if abs(float(torch_out[0][t_pick] - torch_out[0][o_pick])) > rel_tol * scale:
                    argmax_mismatches += 1

            if t_legal.size >= 2:
                top2 = np.sort(t_legal)[::-1][:2]
                min_margin = min(min_margin, float(top2[0] - top2[1]))

    return ParityResult(
        n=n,
        max_abs=max_abs,
        max_rel=max_rel,
        argmax_mismatches=argmax_mismatches,
        min_margin=0.0 if min_margin == float("inf") else min_margin,
        rel_tol=rel_tol,
    )


def export(
    model: torch.nn.Module,
    out_path: str,
    f_dim: int,
    i_dim: int,
    n_actions: int,
) -> _ExportWrapper:
    """Trace ``model`` through ``_ExportWrapper`` and write the ONNX graph to
    ``out_path``. Returns the wrapper (already in eval mode) so the caller can
    run the parity gate against the exact module that was exported."""
    wrapper = _ExportWrapper(model)
    wrapper.eval()
    f, i, mask = _example_inputs(f_dim, i_dim, n_actions)
    with torch.no_grad():
        torch.onnx.export(
            wrapper,
            (f, i, mask),
            out_path,
            input_names=["f", "i", "mask"],
            output_names=["logits"],
            opset_version=17,
            # torch >= 2.5's default exporter is dynamo-based and pulls in
            # `onnxscript` (not one of this repo's pinned deps); the legacy
            # TorchScript-tracing exporter needs only `onnx` itself and is
            # what the brief's opset_version=17 / fixed-batch-1 contract
            # targets, so pin to it explicitly rather than depend on
            # whichever exporter happens to be torch's current default.
            dynamo=False,
        )
    return wrapper


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ckpt", nargs="?", default=None,
        help="checkpoint path (.pt) to export; omit when --stub is given")
    parser.add_argument("--out", required=True, help="output .onnx path")
    parser.add_argument(
        "--stub", action="store_true",
        help="export the checkpoint-free stub model instead of a real checkpoint")
    parser.add_argument(
        "--card-obs", default="hybrid",
        help="run env card-obs mode (default: hybrid, matching training)")
    parser.add_argument("--gate-n", type=int, default=DEFAULT_GATE_N)
    parser.add_argument(
        "--gate-rel-tol", type=float, default=DEFAULT_GATE_REL_TOL,
        help="parity tolerance RELATIVE to each sample's logit scale (default: "
             f"{DEFAULT_GATE_REL_TOL:g}). Replaces the old absolute --gate-threshold, "
             "which tracked model width rather than export faithfulness — see parity_gate.")
    args = parser.parse_args(argv)

    if args.stub and args.ckpt is not None:
        parser.error("--stub takes no checkpoint path")
    if not args.stub and args.ckpt is None:
        parser.error("a checkpoint path is required unless --stub is given")

    layout = run_env.run_obs_layout(args.card_obs)
    f_dim, i_dim, n_actions = layout.f_dim, layout.i_dim, run_env.N_ACTIONS

    if args.stub:
        model: torch.nn.Module = _StubModel()
        model.eval()
    else:
        model, _ckpt = load_agent(
            args.ckpt, env_kind="run", obs_dim=(f_dim, i_dim), n_actions=n_actions,
            card_obs=args.card_obs, device="cpu")

    wrapper = export(model, args.out, f_dim, i_dim, n_actions)

    result = parity_gate(
        wrapper, args.out, f_dim, i_dim, n_actions, args.gate_n, args.gate_rel_tol)
    if not result.passed:
        os.remove(args.out)
        print(f"PARITY GATE FAILED: {result.describe()}; deleted {args.out}",
              file=sys.stderr)
        sys.exit(1)

    print(
        f"wrote {args.out} (f_dim={f_dim} i_dim={i_dim} n_actions={n_actions}); "
        f"{result.describe()}")


if __name__ == "__main__":
    main()
