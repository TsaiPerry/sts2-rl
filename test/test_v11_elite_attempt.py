"""v11.1: reward_elite_attempt + the elites_fought attempts counter.

Default OFF: a default-constructed env must be bit-identical to today's
behavior. The attempt tally fires on the FIRST answered combat decision
inside an elite room (per-room (act, floor) dedup, same as the win tally),
so a death at the elite — which never reaches the rewards screen and is
invisible to `ep_elites_won` — still counts as fought. Scripted the same
way as the v8 potion-ledger tests: monkeypatch `_translate`/
`_count_behavior`-adjacent seams so single step() calls are test-driven.
"""
import argparse
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind, DecisionRequest
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.vec_env import EnvSpec, build_env


def _combat_request(env, room_type) -> DecisionRequest:
    """A COMBAT DecisionRequest carrying only what the tallies read
    (`combat.room_type`); `_build_obs` stubbed so the fake combat object
    never reaches the real obs writer (same idiom as test_v8_rewards)."""
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    # phase=None keeps the end-turn tally branch inert (it checks for
    # Phase.PLAYER_TURN) — this file exercises `_count_behavior` LIVE.
    return DecisionRequest(
        kind=DecisionKind.COMBAT, run=env._run,
        combat=SimpleNamespace(room_type=room_type, phase=None))


def _step_combat(env, room_type):
    env._request = _combat_request(env, room_type)
    env._translate = lambda action, request: 0
    env._switch = lambda answer: None
    return env.step(0)


def test_default_kwargs_inert():
    env = STS2RunEnv()
    assert env._reward_elite_attempt == 0.0


def test_attempt_fires_once_per_elite_room():
    env = STS2RunEnv(reward_elite_attempt=0.2)
    env.reset(seed=0)

    _, r1, *_ = _step_combat(env, RoomType.ELITE)
    assert r1 == pytest.approx(0.2)
    assert env._ep_elites_fought == 1

    # Second decision in the SAME room (same act/floor): no re-pay.
    _, r2, *_ = _step_combat(env, RoomType.ELITE)
    assert r2 == pytest.approx(0.0)
    assert env._ep_elites_fought == 1

    # A different floor is a different room: pays again.
    env._run.total_floor += 1
    _, r3, *_ = _step_combat(env, RoomType.ELITE)
    assert r3 == pytest.approx(0.2)
    assert env._ep_elites_fought == 2


def test_non_elite_combat_pays_nothing():
    env = STS2RunEnv(reward_elite_attempt=0.2)
    env.reset(seed=0)
    _, reward, *_ = _step_combat(env, RoomType.MONSTER)
    assert reward == 0.0
    assert env._ep_elites_fought == 0


def test_attempt_counts_without_a_win():
    # The whole point: the fought tally moves with NO rewards screen ever
    # appearing (a death at the elite), while the win tally stays 0.
    env = STS2RunEnv(reward_elite_attempt=0.2)
    env.reset(seed=0)
    _step_combat(env, RoomType.ELITE)
    assert env._ep_elites_fought == 1
    assert env._ep_elites_won == 0


def test_info_exports_fought_at_episode_end():
    from sts2_rl.driver import RunResult

    env = STS2RunEnv(reward_elite_attempt=0.0, reward_win=0.0, win_hp_bonus=0.0)
    env.reset(seed=0)
    _step_combat(env, RoomType.ELITE)

    def _end(answer):
        env._result = RunResult(victory=True, hp=env._run.hp, max_hp=env._run.max_hp,
                                gold=0, floor=env._run.total_floor,
                                act_index=env._run.act_index,
                                deck_size=len(env._run.deck), decisions=1)
        env._request = None

    # Leave the live request in place — step() only runs `_switch` when a
    # request is being answered (v8 end-step idiom).
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = _end
    _, _, terminated, _, info = env.step(0)
    assert terminated
    assert info["ep_elites_fought"] == 1
    assert info["ep_elites_won"] == 0


def test_default_env_reward_unchanged_with_attempt_off():
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

    assert _roll(STS2RunEnv(), seed=7) == _roll(STS2RunEnv(reward_elite_attempt=0.0), seed=7)


def test_envspec_threads_to_run_env():
    assert build_env(EnvSpec(kind="run", reward_elite_attempt=0.2))._reward_elite_attempt == 0.2
    assert build_env(EnvSpec(kind="run"))._reward_elite_attempt == 0.0


def test_env_spec_threads_flag():
    import train_torch
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            reward_elite_attempt=0.2)
    assert train_torch.env_spec(ns).reward_elite_attempt == 0.2
