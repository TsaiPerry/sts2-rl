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
ONNX graph via ``onnxruntime``, and the run fails — deleting the ``.onnx``
file and exiting nonzero — unless ``max|Δ| < threshold`` (default 1e-4) at
every one of them. A broken export is therefore never left on disk.

Dependencies (``py -m pip install onnx onnxruntime``): installed here as
onnx 1.22.0 / onnxruntime 1.28.0, on top of this machine's torch
2.13.0+cu130. Export and the parity gate both run on CPU (``device="cpu"``)
regardless of what training used — the C# consumer runs CPU ONNX Runtime.
"""
from __future__ import annotations

import argparse
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
DEFAULT_GATE_THRESHOLD = 1e-4


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


def parity_gate(
    wrapper: torch.nn.Module,
    onnx_path: str,
    f_dim: int,
    i_dim: int,
    n_actions: int,
    n: int = DEFAULT_GATE_N,
    threshold: float = DEFAULT_GATE_THRESHOLD,
) -> float:
    """Push ``n`` random ``(f, i, mask)`` triples through ``wrapper`` (torch)
    and the ``onnx_path`` graph (onnxruntime) and return the observed
    ``max|Δ|``. Does not raise or delete anything itself — the CLI decides
    what to do with the result, so tests can call this directly too."""
    import onnxruntime as ort

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(12345)
    wrapper.eval()
    max_delta = 0.0
    with torch.no_grad():
        for _ in range(n):
            f, i, mask = _random_batch(rng, f_dim, i_dim, n_actions)
            torch_out = wrapper(
                torch.from_numpy(f), torch.from_numpy(i), torch.from_numpy(mask)
            ).numpy()
            (onnx_out,) = sess.run(None, {"f": f, "i": i, "mask": mask})
            max_delta = max(max_delta, float(np.abs(torch_out - onnx_out).max()))
    return max_delta


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
    parser.add_argument("--gate-threshold", type=float, default=DEFAULT_GATE_THRESHOLD)
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

    max_delta = parity_gate(
        wrapper, args.out, f_dim, i_dim, n_actions, args.gate_n, args.gate_threshold)
    if max_delta >= args.gate_threshold:
        os.remove(args.out)
        print(
            f"PARITY GATE FAILED: max|delta|={max_delta:.3e} >= "
            f"threshold {args.gate_threshold:.1e} over {args.gate_n} samples; "
            f"deleted {args.out}", file=sys.stderr)
        sys.exit(1)

    print(
        f"wrote {args.out} (f_dim={f_dim} i_dim={i_dim} n_actions={n_actions}); "
        f"parity gate max|delta|={max_delta:.3e} < {args.gate_threshold:.1e} "
        f"over {args.gate_n} samples")


if __name__ == "__main__":
    main()
