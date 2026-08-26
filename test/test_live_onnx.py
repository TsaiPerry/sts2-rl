"""Task 6 (SpireBot live bot): the ONNX exporter's tests.

``sts2_rl/live/export_onnx.py`` exports the run-scale policy's masked action
logits as a fixed-shape ONNX graph for the future C# mod's ``OnnxPolicy``.
The stub test needs no checkpoint (``--stub``); the checkpoint-parity test
activates for real once a local run-scale checkpoint at the CURRENT obs
schema exists (Task 15) — every checkpoint under ``runs/`` today predates the
"f"/"i" Dict generation (obs_schema well below ``RUN_OBS_SCHEMA_VERSION``),
so it stays skipped on this machine.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from sts2_rl import models, run_env
from sts2_rl.live.export_onnx import (
    DEFAULT_GATE_REL_TOL,
    _MASK_FILL,
    parity_gate,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_stub_export_and_parity(tmp_path):
    out = tmp_path / "stub.onnx"
    subprocess.run(
        [sys.executable, "-m", "sts2_rl.live.export_onnx", "--stub", "--out", str(out)],
        check=True, cwd=str(REPO_ROOT))

    import onnxruntime as ort

    sess = ort.InferenceSession(str(out))
    layout = run_env.run_obs_layout()
    f_dim, i_dim, n = layout.f_dim, layout.i_dim, run_env.N_ACTIONS

    rng = np.random.default_rng(0)
    f = rng.random((1, f_dim), dtype=np.float32)
    i = rng.integers(0, 5, (1, i_dim)).astype(np.int64)
    mask = np.zeros((1, n), dtype=bool)
    mask[0, [0, 3, 7]] = True
    (logits,) = sess.run(None, {"f": f, "i": i, "mask": mask})

    assert logits.shape == (1, n)
    assert (logits[0, ~mask[0]] < -1e7).all()
    assert np.allclose(logits[0, mask[0]], 0.0)


def _find_current_schema_checkpoint() -> str | None:
    """A local ``runs/*.pt`` run-scale ``entset`` checkpoint stamped at
    today's ``RUN_OBS_SCHEMA_VERSION``, or ``None``. ``checkpoints.
    check_checkpoint`` refuses anything off that schema outright (no
    migration path — see its module docstring), so this probe treats a stale
    stamp the same as "no checkpoint available" rather than letting
    ``load_agent`` raise inside the test."""
    runs_dir = REPO_ROOT / "runs"
    if not runs_dir.is_dir():
        return None
    # Newest first: exercise the checkpoint a deploy would actually export,
    # not whichever stale-but-loadable one sorts first alphabetically.
    for path in sorted(glob.glob(str(runs_dir / "*.pt")),
                       key=os.path.getmtime, reverse=True):
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
        except Exception:
            continue
        if ckpt.get("env_kind") not in ("run", "column"):
            continue
        if ckpt.get("arch") != "entset":
            continue
        if ckpt.get("obs_schema") != run_env.RUN_OBS_SCHEMA_VERSION:
            continue
        # check_checkpoint also refuses a stale entset head STRUCTURE (e.g.
        # head_version 4 pre-v22 checkpoints, which need tools/migrate_headv5
        # first) — same "no checkpoint available" treatment as a stale schema.
        if ckpt.get("head_version", 1) != models.ENTSET_HEAD_VERSION:
            continue
        return path
    return None


_CKPT_PATH = _find_current_schema_checkpoint()


@pytest.mark.skipif(
    _CKPT_PATH is None,
    reason="no local run-scale entset checkpoint at the current RUN_OBS_SCHEMA_VERSION "
           "(every runs/*.pt here predates the f/i-Dict generation)")
def test_checkpoint_export_matches_torch_parity(tmp_path):
    from sts2_rl.checkpoints import load_agent
    from sts2_rl.live.export_onnx import _ExportWrapper

    layout = run_env.run_obs_layout()
    f_dim, i_dim, n = layout.f_dim, layout.i_dim, run_env.N_ACTIONS

    model, _ckpt = load_agent(
        _CKPT_PATH, env_kind="run", obs_dim=(f_dim, i_dim), n_actions=n, device="cpu")

    out = tmp_path / "real.onnx"
    subprocess.run(
        [sys.executable, "-m", "sts2_rl.live.export_onnx", _CKPT_PATH, "--out", str(out)],
        check=True, cwd=str(REPO_ROOT))

    wrapper = _ExportWrapper(model)
    result = parity_gate(wrapper, str(out), f_dim, i_dim, n, n=32)
    assert result.passed, result.describe()
    # The gate's own criteria, asserted explicitly so a regression in either one
    # fails here and not only inside `passed`.
    assert result.argmax_mismatches == 0
    assert result.max_rel < DEFAULT_GATE_REL_TOL


def _fake_session(logits_by_call):
    """A stand-in for an ``onnxruntime.InferenceSession`` that replays canned
    logits, so the gate's decision logic can be tested without exporting a
    graph (and without a checkpoint — these tests must run on any machine)."""

    class _Sess:
        def __init__(self):
            self.calls = 0

        def run(self, _outputs, _inputs):
            out = logits_by_call[min(self.calls, len(logits_by_call) - 1)]
            self.calls += 1
            return (np.asarray(out, dtype=np.float32).reshape(1, -1),)

    return _Sess()


class _FixedLogits(torch.nn.Module):
    """Torch side of the same canned comparison — ignores its inputs and
    returns a fixed logit row, masked the way the real models mask."""

    def __init__(self, row):
        super().__init__()
        self.row = torch.tensor(row, dtype=torch.float32)

    def forward(self, f, i, mask):
        return self.row.unsqueeze(0).masked_fill(~mask, _MASK_FILL)


def _gate_over(torch_row, onnx_rows, mask_row, **kw):
    """Run `parity_gate` with both sides canned and one fixed mask."""
    n = len(torch_row)
    mask = np.asarray(mask_row, dtype=bool).reshape(1, n)
    return parity_gate(
        _FixedLogits(torch_row), _fake_session(onnx_rows), 4, 2, n,
        n=len(onnx_rows), _mask_override=mask, **kw)


def test_gate_passes_on_float_noise_at_large_logit_scale():
    """The v23 export's actual failure mode: |logits| ~ 90 with a ~2e-4 float32
    accumulation delta. Absolutely that is > 1e-4; relative to the logit scale
    it is ~2e-6, the argmax is unchanged, and the export is faithful."""
    torch_row = [90.0, 40.0, 10.0]
    onnx_rows = [[90.0002, 40.0001, 9.99985]]
    r = _gate_over(torch_row, onnx_rows, [True, True, True])
    assert r.max_abs > 1e-4          # would have failed the old absolute gate
    assert r.max_rel < 1e-5
    assert r.argmax_mismatches == 0
    assert r.passed


def test_gate_fails_when_argmax_flips_on_a_real_margin():
    """A genuinely broken export: the two candidates are 5.0 apart in torch, so
    onnxruntime preferring the other one is a real disagreement, not a tie."""
    torch_row = [10.0, 5.0, 1.0]
    onnx_rows = [[4.0, 6.0, 1.0]]
    r = _gate_over(torch_row, onnx_rows, [True, True, True])
    assert r.argmax_mismatches == 1
    assert not r.passed
    assert "argmax" in r.describe()


def test_gate_tolerates_a_tiebreak_flip_between_indistinguishable_actions():
    """Two legal actions the model rates identically to within tolerance: which
    one wins is arbitrary, so a flip is not a parity failure."""
    torch_row = [7.0, 7.0, 1.0]
    onnx_rows = [[6.99999, 7.00001, 1.0]]
    r = _gate_over(torch_row, onnx_rows, [True, True, True])
    assert r.argmax_mismatches == 0
    assert r.passed


def test_gate_fails_on_a_gross_delta_even_without_an_argmax_flip():
    """The catastrophic-export case the gate exists for (pruned inputs, wrong
    opset semantics): huge deltas, but the ordering happens to survive."""
    torch_row = [10.0, 5.0, 1.0]
    onnx_rows = [[40.0, 5.0, 1.0]]
    r = _gate_over(torch_row, onnx_rows, [True, True, True])
    assert r.argmax_mismatches == 0
    assert r.max_rel > DEFAULT_GATE_REL_TOL
    assert not r.passed


def test_gate_ignores_masked_positions():
    """Illegal positions are `_MASK_FILL` on both sides and carry no decision
    weight; a difference there must not move any of the gate's metrics."""
    torch_row = [10.0, 5.0, 1.0]
    onnx_rows = [[10.0, 5.0, 999.0]]     # position 2 is masked off
    r = _gate_over(torch_row, onnx_rows, [True, True, False])
    assert r.max_abs == 0.0
    assert r.argmax_mismatches == 0
    assert r.passed


def test_gate_does_not_demand_absurd_precision_near_zero():
    """With a unit floor on the scale, a near-zero logit row is held to the
    tolerance absolutely rather than to `delta / ~0`, which would be infinite."""
    torch_row = [0.001, 0.0005, 0.0]
    onnx_rows = [[0.001005, 0.0005, 0.0]]
    r = _gate_over(torch_row, onnx_rows, [True, True, True])
    assert r.max_rel < DEFAULT_GATE_REL_TOL
    assert r.passed
