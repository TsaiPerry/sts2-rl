"""v9 reward fixes (plan 2026-08-12-v9-rest-potion-fix): rest-heal shaping
knee cap + death-only potion expiry. Both default OFF: a default env stays
bit-identical (test_v8_rewards pins the baseline)."""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind, DecisionRequest, REST_HEAL, REST_SMITH
from sts2_rl.run_env import STS2RunEnv, _hp_potential

KNEE = 0.35
LOW_SHARE = 0.7


def _phi(r):
    return _hp_potential(r, KNEE, LOW_SHARE)


def _rest_step(env, hp_before, hp_after, answer, max_hp=100):
    """One step() answering a REST decision with `answer`, whose only run-state
    change is HP — same seam-monkeypatch isolation as test_v8_rewards.
    _build_obs is stubbed (as test_v8_rewards._combat_request does) because a
    hand-built REST request may lack fields the real obs writer reads."""
    env._run.hp = hp_before
    env._run.max_hp = max_hp
    env._request = DecisionRequest(kind=DecisionKind.REST, run=env._run, combat=None)
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    env._translate = lambda action, request: answer
    env._count_behavior = lambda request, answer: None
    env._switch = lambda a: setattr(env._run, "hp", hp_after)
    return env.step(0)


def test_rest_heal_above_knee_earns_zero_with_cap():
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(0.0, abs=1e-9)


def test_rest_heal_from_below_knee_caps_at_knee():
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=20, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(4.0 * (_phi(0.35) - _phi(0.20)), abs=1e-9)


def test_rest_smith_keeps_full_shaping():
    # Source-specificity: only the REST_HEAL answer is capped.
    env = STS2RunEnv(hp_potential_scale=4.0, rest_heal_shaping_knee_cap=True)
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_SMITH)
    assert reward == pytest.approx(4.0 * (_phi(1.00) - _phi(0.80)), abs=1e-9)


def test_rest_heal_uncapped_without_flag():
    env = STS2RunEnv(hp_potential_scale=4.0)   # flag defaults off
    env.reset(seed=0)
    _, reward, *_ = _rest_step(env, hp_before=80, hp_after=100, answer=REST_HEAL)
    assert reward == pytest.approx(4.0 * (_phi(1.00) - _phi(0.80)), abs=1e-9)


def test_v9_kwargs_default_inert():
    env = STS2RunEnv()
    assert env._rest_heal_shaping_knee_cap is False


def _potion(env):
    run = env._run
    run.potions[run.potions.index(None)] = SimpleNamespace(id="__test_placeholder__")


def _pickup_step(env):
    """Real step() so _belt_base syncs (see test_v8_rewards._seed_potion)."""
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = lambda a: _potion(env)
    env.step(0)


def _death_step(env):
    def _die(a):
        env._run.hp = 0
        env._result = SimpleNamespace(victory=False, hp=0, max_hp=env._run.max_hp)
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = _die
    env._info = lambda: {}
    return env.step(0)


def _death_reward(expiry: bool) -> float:
    env = STS2RunEnv(potion_potential_scale=0.3, potion_death_expiry=expiry)
    env.reset(seed=0)
    _pickup_step(env)
    _pickup_step(env)
    _, reward, terminated, *_ = _death_step(env)
    assert terminated
    return reward


def test_death_expires_each_held_potion_at_minus_k():
    assert _death_reward(True) - _death_reward(False) == pytest.approx(-0.6)


def test_win_keeps_held_potion_credit():
    def _win_reward(expiry):
        env = STS2RunEnv(potion_potential_scale=0.3, potion_death_expiry=expiry)
        env.reset(seed=0)
        _pickup_step(env)

        def _w(a):
            env._result = SimpleNamespace(
                victory=True, hp=env._run.hp, max_hp=env._run.max_hp)
        env._translate = lambda action, request: 0
        env._count_behavior = lambda request, answer: None
        env._switch = _w
        env._info = lambda: {}
        _, reward, terminated, *_ = env.step(0)
        assert terminated
        return reward
    assert _win_reward(True) == pytest.approx(_win_reward(False))


def test_potion_death_expiry_default_off():
    assert STS2RunEnv()._potion_death_expiry is False


from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_v9_flags_reach_run_env():
    spec = EnvSpec(kind="run", rest_heal_shaping_knee_cap=True,
                   potion_death_expiry=True)
    env = build_env(spec)
    assert env._rest_heal_shaping_knee_cap is True
    assert env._potion_death_expiry is True


def test_envspec_v9_flags_default_off():
    env = build_env(EnvSpec(kind="run"))
    assert env._rest_heal_shaping_knee_cap is False
    assert env._potion_death_expiry is False
