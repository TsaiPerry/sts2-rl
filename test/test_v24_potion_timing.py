"""v24 potion timing refund (`potion_timing_refund`): the belt ledger's
-k release charge is partially refunded (+refund) when a drink resolves
DURING an elite/boss combat with a non-AnyTime potion. Everything else --
normal-room drinks, out-of-combat AnyTime overlay drinks, non-drink belt
losses, discards -- keeps the full -k. Default OFF (0.0) = bit-identical
env (same contract as every other reward knob).

Scripted like test_v8_rewards' ledger tests: `_translate`/`_count_behavior`/
`_switch` monkeypatched so one step() isolates the arithmetic. The combat
stub carries a `player` (hp + potions) because the drink-classification
branch requires one to treat the request as in-combat.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind, DecisionRequest, POTION_ACTION_BASE
from sts2_rl.potions import USAGE_ANY_TIME
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import STS2RunEnv


def _add_potion(env, usage=None) -> None:
    run = env._run
    kw = {"id": "__test_placeholder__"}
    if usage is not None:
        kw["usage"] = usage
    run.potions[run.potions.index(None)] = SimpleNamespace(**kw)


def _remove_potion(env) -> None:
    run = env._run
    idx = next(i for i, p in enumerate(run.potions) if p is not None)
    run.potions[idx] = None


def _seed_potion(env, usage=None) -> None:
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _add_potion(env, usage)
    env.step(0)


def _combat_request(env, room_type) -> DecisionRequest:
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    run = env._run
    return DecisionRequest(
        kind=DecisionKind.COMBAT, run=run,
        combat=SimpleNamespace(
            room_type=room_type,
            player=SimpleNamespace(hp=run.hp, potions=run.potions)))


def _drink_step(env, room_type):
    env._request = _combat_request(env, room_type)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    return reward


def test_default_kwarg_inert():
    env = STS2RunEnv()
    assert env._potion_timing_refund == 0.0


def test_elite_drink_pays_the_refund():
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env)
    reward = _drink_step(env, RoomType.ELITE)
    assert reward == pytest.approx(-0.25)   # -0.5 release + 0.25 refund
    assert env._ep_potions_used == 1


def test_boss_drink_pays_the_refund():
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env)
    reward = _drink_step(env, RoomType.BOSS)
    assert reward == pytest.approx(-0.25)


def test_normal_room_drink_keeps_full_charge():
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env)
    reward = _drink_step(env, RoomType.MONSTER)
    assert reward == pytest.approx(-0.5)


def test_any_time_potion_excluded_in_elite():
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env, usage=USAGE_ANY_TIME)
    reward = _drink_step(env, RoomType.ELITE)
    assert reward == pytest.approx(-0.5)


def test_out_of_combat_overlay_drink_keeps_full_charge():
    """An AnyTime overlay drink on a non-combat request classifies as
    room='none' and must never qualify, whatever the potion."""
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env)
    env._request = DecisionRequest(kind=DecisionKind.EVENT, run=env._run)
    env._translate = lambda action, request: POTION_ACTION_BASE + 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(-0.5)


def test_non_drink_loss_in_elite_keeps_full_charge():
    """A belt loss not answered via a potion action never qualifies, even
    with the combat request sitting in an elite room."""
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.25)
    env.reset(seed=0)
    _seed_potion(env)
    env._request = _combat_request(env, RoomType.ELITE)
    env._translate = lambda action, request: 0   # NOT a potion-use answer
    env._count_behavior = lambda request, answer: None
    env._switch = lambda answer: _remove_potion(env)
    _, reward, *_ = env.step(0)
    assert reward == pytest.approx(-0.5)


def test_flag_reaches_the_built_run_env():
    from sts2_rl.vec_env import EnvSpec, build_env
    env = build_env(EnvSpec(kind="run", potion_timing_refund=0.25))
    assert env._potion_timing_refund == 0.25
    dflt = build_env(EnvSpec(kind="run"))
    assert dflt._potion_timing_refund == 0.0


def test_refund_zero_is_bit_identical():
    env = STS2RunEnv(potion_potential_scale=0.5, potion_timing_refund=0.0)
    env.reset(seed=0)
    _seed_potion(env)
    reward = _drink_step(env, RoomType.ELITE)
    assert reward == pytest.approx(-0.5)
