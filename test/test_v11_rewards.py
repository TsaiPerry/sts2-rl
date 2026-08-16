"""v11 reward term (plan 2026-08-14-v11-combat-detour Task 1): reward_boss.
Default OFF: a default-constructed env must be bit-identical to today's
behavior. Scripted the same way as the v8 reward tests: monkeypatch
`_translate`/`_count_behavior`/`_switch` so a single step() call is driven
entirely by the test."""
import numpy as np
import pytest

from sts2_rl.driver import RunResult
from sts2_rl.run_env import STS2RunEnv


def _scripted_step(env, mutate):
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = mutate
    return env.step(0)


def _roll(env, seed, steps=400):
    obs, _ = env.reset(seed=seed)
    total = 0.0
    for _ in range(steps):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    return total


def test_default_kwargs_inert_boss():
    env = STS2RunEnv()
    assert env._reward_boss == 0.0


def test_boss_reward_fires_once_on_act_advance():
    env = STS2RunEnv(reward_boss=3.0)
    env.reset(seed=0)

    def _advance(answer):
        env._run.act_index += 1

    _, reward, terminated, truncated, _ = _scripted_step(env, _advance)
    assert not terminated and not truncated
    assert reward == pytest.approx(3.0)


def test_boss_reward_pays_nothing_on_ordinary_step():
    env = STS2RunEnv(reward_boss=3.0)
    env.reset(seed=0)
    _, reward, terminated, truncated, _ = _scripted_step(env, lambda answer: None)
    assert not terminated and not truncated
    assert reward == 0.0


def test_final_win_pays_reward_win_plus_reward_boss():
    env = STS2RunEnv(reward_boss=3.0, reward_win=12.0, win_hp_bonus=0.0)
    env.reset(seed=0)

    def _end(answer):
        env._result = RunResult(victory=True, hp=env._run.hp, max_hp=env._run.max_hp,
                                gold=0, floor=env._run.total_floor,
                                act_index=env._run.act_index,
                                deck_size=len(env._run.deck), decisions=1)
        env._request = None

    _, reward, terminated, _, _ = _scripted_step(env, _end)
    assert terminated
    assert reward == pytest.approx(15.0)     # 12 win + 3 boss, no double-pay


def test_loss_pays_no_boss_reward():
    env = STS2RunEnv(reward_boss=3.0, reward_win=12.0, reward_loss=0.0)
    env.reset(seed=0)

    def _end(answer):
        env._result = RunResult(victory=False, hp=0, max_hp=env._run.max_hp,
                                gold=0, floor=env._run.total_floor,
                                act_index=env._run.act_index,
                                deck_size=len(env._run.deck), decisions=1)
        env._request = None

    _, reward, terminated, _, _ = _scripted_step(env, _end)
    assert terminated
    assert reward == pytest.approx(0.0)


def test_default_env_reward_unchanged_with_reward_boss_off():
    r_a = _roll(STS2RunEnv(), seed=7)
    r_b = _roll(STS2RunEnv(reward_boss=0.0), seed=7)
    assert r_a == r_b
