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
    from sts2_rl.live.export_onnx import _ExportWrapper, parity_gate

    layout = run_env.run_obs_layout()
    f_dim, i_dim, n = layout.f_dim, layout.i_dim, run_env.N_ACTIONS

    model, _ckpt = load_agent(
        _CKPT_PATH, env_kind="run", obs_dim=(f_dim, i_dim), n_actions=n, device="cpu")

    out = tmp_path / "real.onnx"
    subprocess.run(
        [sys.executable, "-m", "sts2_rl.live.export_onnx", _CKPT_PATH, "--out", str(out)],
        check=True, cwd=str(REPO_ROOT))

    wrapper = _ExportWrapper(model)
    max_delta = parity_gate(wrapper, str(out), f_dim, i_dim, n, n=32, threshold=1e-4)
    assert max_delta < 1e-4
