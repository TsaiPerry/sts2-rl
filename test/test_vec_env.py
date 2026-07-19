"""Serial vs subprocess env stepping must be indistinguishable.

The worker layout is a runtime detail: ``train_torch.py`` seeds env *i* by its
global index and the envs share no state, so a fixed seed and a fixed policy
have to produce byte-identical rollouts however the envs are split across
processes. These tests pin that, since a silent divergence would look like a
training regression rather than a bug.
"""
from __future__ import annotations

import numpy as np
import pytest

from sts2_rl.vec_env import (EnvSpec, SerialVecEnv, SubprocVecEnv, _split,
                             make_vec_env, resolve_n_workers)


def _policy(step: int, masks: np.ndarray) -> np.ndarray:
    """A deterministic function of (step, masks) — no model, no hidden state.

    Deterministic so both paths issue the same actions, and mask-dependent so
    a divergence in one env's state shows up as a divergence in the rollout
    rather than being papered over by a constant action.
    """
    rng = np.random.default_rng(9876 + step)
    return np.array([rng.choice(np.flatnonzero(m)) for m in masks], dtype=np.int64)


def _rollout(venv, n_steps: int, seed: int = 0) -> list[tuple]:
    """Everything the trainer consumes, per step, as comparable arrays."""
    obs, masks = venv.reset([seed + i for i in range(venv.num_envs)])
    trace = [(obs.copy(), masks.copy())]
    for t in range(n_steps):
        b = venv.step(_policy(t, masks))
        trace.append((
            b.obs.copy(), b.rewards.copy(), b.terminated.copy(),
            b.truncated.copy(), b.masks.copy(), b.successes.copy(),
            sorted(b.final_obs), [b.final_obs[i].copy() for i in sorted(b.final_obs)],
        ))
        obs, masks = b.obs, b.masks
    return trace


def _assert_traces_equal(a: list[tuple], b: list[tuple]) -> None:
    assert len(a) == len(b)
    for t, (step_a, step_b) in enumerate(zip(a, b)):
        assert len(step_a) == len(step_b)
        for field, (x, y) in enumerate(zip(step_a, step_b)):
            if isinstance(x, list) and x and isinstance(x[0], np.ndarray):
                assert len(x) == len(y), f"step {t} field {field}"
                assert all(np.array_equal(p, q) for p, q in zip(x, y)), \
                    f"step {t} field {field}"
            else:
                assert np.array_equal(x, y), f"step {t} field {field}: {x!r} != {y!r}"


# ── layout helpers (no processes) ─────────────────────────────────────────

def test_split_is_even_and_total_preserving():
    assert _split(8, 4) == [2, 2, 2, 2]
    assert _split(8, 3) == [3, 3, 2]
    assert _split(3, 3) == [1, 1, 1]
    for n_envs in range(1, 17):
        for n_workers in range(1, n_envs + 1):
            counts = _split(n_envs, n_workers)
            assert sum(counts) == n_envs and min(counts) >= 1
            assert max(counts) - min(counts) <= 1


def test_resolve_n_workers():
    assert resolve_n_workers(8, 0) == 0            # the default: serial path
    assert resolve_n_workers(8, 4) == 4
    assert resolve_n_workers(4, 99) == 4           # never more workers than envs
    with pytest.raises(ValueError):
        resolve_n_workers(8, -1)


def test_make_vec_env_picks_the_serial_path_for_one_worker():
    # A single worker is the serial loop plus a pipe — not worth a process.
    spec = EnvSpec(kind="combat", encounter="fuzzy_wurm_weak")
    venv = make_vec_env(spec, n_envs=2, n_workers=1)
    try:
        assert isinstance(venv, SerialVecEnv)
        assert venv.n_workers == 0
    finally:
        venv.close()


def test_subproc_rejects_more_workers_than_envs():
    with pytest.raises(ValueError):
        SubprocVecEnv(EnvSpec(kind="combat"), n_envs=2, n_workers=3)


# ── equivalence ───────────────────────────────────────────────────────────

def test_combat_rollouts_are_identical_serial_vs_workers():
    spec = EnvSpec(kind="combat")
    serial = SerialVecEnv(spec, n_envs=4)
    try:
        expected = _rollout(serial, n_steps=300)
    finally:
        serial.close()

    # 3 workers over 4 envs: an uneven split, so a slice-offset bug in the
    # gather (final_obs indices especially) can't hide behind symmetry.
    workers = SubprocVecEnv(spec, n_envs=4, n_workers=3)
    try:
        assert (workers.obs_dim, workers.n_actions) == (serial.obs_dim, serial.n_actions)
        _assert_traces_equal(expected, _rollout(workers, n_steps=300))
    finally:
        workers.close()


def test_run_env_rollouts_are_identical_serial_vs_workers():
    """Smoke test for the greenlet-driven env: whole envs stay in one process,
    so the driver greenlet never has to cross a pipe."""
    spec = EnvSpec(kind="column")
    serial = SerialVecEnv(spec, n_envs=2)
    try:
        expected = _rollout(serial, n_steps=60)
    finally:
        serial.close()

    workers = SubprocVecEnv(spec, n_envs=2, n_workers=2)
    try:
        _assert_traces_equal(expected, _rollout(workers, n_steps=60))
    finally:
        workers.close()


def test_workers_exit_with_close():
    venv = SubprocVecEnv(EnvSpec(kind="combat"), n_envs=2, n_workers=2)
    procs = list(venv._procs)
    venv.reset([0, 1])
    venv.close()
    venv.close()                                   # idempotent
    assert not any(p.is_alive() for p in procs)


# ── auto-reset semantics (serial path is the reference implementation) ────

def test_auto_reset_returns_the_reset_observation_and_its_mask():
    venv = SerialVecEnv(EnvSpec(kind="combat", encounter="fuzzy_wurm_weak"), n_envs=1)
    try:
        _, masks = venv.reset([7])
        for t in range(2000):
            b = venv.step(_policy(t, masks))
            masks = b.masks
            if b.terminated[0] or b.truncated[0]:
                # obs/masks describe the FRESH combat, so the next step is a
                # legal move in it — no reset call in the training loop.
                assert masks[0].any(), "reset env must offer legal actions"
                venv.step(_policy(t + 1, masks))
                break
        else:
            pytest.fail("no episode ended in 2000 steps")
    finally:
        venv.close()


def test_final_obs_is_supplied_for_truncation_only():
    """The trainer bootstraps gamma*V(final_obs) on truncation; a natural
    termination bootstraps 0 and its final obs would be dead weight."""
    venv = SerialVecEnv(EnvSpec(kind="combat", encounter="fuzzy_wurm_weak"), n_envs=1)
    try:
        _, masks = venv.reset([3])
        saw_terminated = False
        for t in range(4000):
            b = venv.step(_policy(t, masks))
            masks = b.masks
            assert set(b.final_obs) == set(np.flatnonzero(b.truncated & ~b.terminated))
            saw_terminated |= bool(b.terminated[0])
        assert saw_terminated, "expected at least one natural termination"
    finally:
        venv.close()
