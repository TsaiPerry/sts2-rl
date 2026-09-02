import types
import numpy as np
import pytest
from sts2_rl.run_env import run_progress, _FULL_RUN_FLOORS
from sts2_rl.run_env import STS2RunEnv


def _run(total_floor):
    return types.SimpleNamespace(total_floor=total_floor)


def test_full_run_floors_is_positive():
    assert _FULL_RUN_FLOORS > 0


def test_run_progress_zero_at_start():
    assert run_progress(_run(0)) == 0.0


def test_run_progress_reaches_one_and_clamps():
    assert run_progress(_run(_FULL_RUN_FLOORS)) == 1.0
    # Past the normalizer it clamps, never exceeds 1.0.
    assert run_progress(_run(_FULL_RUN_FLOORS * 3)) == 1.0


def test_run_progress_is_monotone_nondecreasing():
    vals = [run_progress(_run(f)) for f in range(0, int(_FULL_RUN_FLOORS) + 5)]
    assert all(b >= a for a, b in zip(vals, vals[1:]))


def _drive_first_legal(env, seed, max_steps=5000):
    """Play the first legal action every step until the episode ends.
    Returns (total_reward, terminated, truncated, progress_at_start)."""
    obs, _ = env.reset(seed=seed)
    p0 = run_progress(env._run)
    total = 0.0
    for _ in range(max_steps):
        mask = env.action_masks()
        action = int(np.argmax(mask))          # first True = a legal action
        obs, r, term, trunc, info = env.step(action)
        total += r
        if term or trunc:
            return total, term, trunc, p0
    return total, False, True, p0


def test_progress_shaping_telescopes_to_start_potential():
    # Only progress shaping is on: floor payment and win bonus off. The
    # per-step DeltaPhi sum over a completed episode telescopes to
    # c*(Phi(terminal) - Phi(s0)) = -c*Phi(s0), regardless of win/loss.
    c = 2.0
    env = STS2RunEnv(progress_potential_scale=c, floor_reward=0.0, reward_win=0.0)
    total, term, trunc, p0 = _drive_first_legal(env, seed=0)
    assert term and not trunc, "first-legal policy should reach a real terminal"
    assert total == pytest.approx(-c * p0, abs=1e-4)


def test_progress_shaping_off_by_default_gives_zero_reward():
    # scale 0 + no other terms => every step's reward is exactly 0.
    env = STS2RunEnv(progress_potential_scale=0.0, floor_reward=0.0, reward_win=0.0)
    total, term, trunc, _ = _drive_first_legal(env, seed=0)
    assert term and not trunc
    assert total == pytest.approx(0.0, abs=1e-6)


def test_reward_anneal_present_and_zero_by_default():
    # No elite/boss terms configured => subtotal is 0.0 every step, but the key
    # is always present (the trainer reads it unconditionally).
    env = STS2RunEnv(floor_reward=1.0, reward_win=3.0)
    env.reset(seed=1)
    for _ in range(50):
        mask = env.action_masks()
        _, _, term, trunc, info = env.step(int(np.argmax(mask)))
        assert "reward_anneal" in info
        assert info["reward_anneal"] == 0.0
        if term or trunc:
            break


def test_reward_anneal_equals_elite_boss_portion():
    # Two same-seed episodes: one with elite/boss terms, one without. Per step,
    # (reward_on - reward_off) must equal the ON env's reported subtotal.
    common = dict(floor_reward=1.0, reward_win=3.0)
    on = STS2RunEnv(elite_rewards_by_act=(2.0, 3.0, 4.0),
                    elite_attempt_rewards_by_act=(1.0, 1.5, 2.0),
                    reward_boss=3.0, reward_elite_escalator=0.5, **common)
    off = STS2RunEnv(**common)
    on.reset(seed=7)
    off.reset(seed=7)
    for _ in range(5000):
        mask = on.action_masks()
        a = int(np.argmax(mask))
        _, r_on, t_on, tr_on, info_on = on.step(a)
        _, r_off, t_off, tr_off, _ = off.step(a)
        assert (r_on - r_off) == pytest.approx(info_on["reward_anneal"], abs=1e-4)
        if t_on or tr_on:
            break
