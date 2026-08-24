"""v9 reward fixes (plan 2026-08-12-v9-rest-potion-fix): rest-heal shaping
knee cap + death-only potion expiry. Both default OFF: a default env stays
bit-identical (test_v8_rewards pins the baseline)."""
from types import SimpleNamespace

import numpy as np
import pytest

from sts2_rl.combat import Phase
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


# ── v15.1: potion_death_penalty — flat -penalty per potion still held at
# death, ON TOP of the expiry forfeiture. Expiry alone only nets
# hoard-and-die back to 0 (= drink-and-die); the flat penalty prices
# dying while holding strictly BELOW using-then-dying.


def _death_reward_flat(penalty: float) -> float:
    env = STS2RunEnv(potion_death_penalty=penalty)
    env.reset(seed=0)
    _pickup_step(env)
    _pickup_step(env)
    _, reward, terminated, *_ = _death_step(env)
    assert terminated
    return reward


def test_potion_death_penalty_charges_flat_per_held_potion():
    assert (_death_reward_flat(0.3) - _death_reward_flat(0.0)
            == pytest.approx(-0.6))


def test_potion_death_penalty_stacks_with_expiry():
    def _r(penalty):
        env = STS2RunEnv(potion_potential_scale=0.3, potion_death_expiry=True,
                         potion_death_penalty=penalty)
        env.reset(seed=0)
        _pickup_step(env)
        _, reward, *_ = _death_step(env)
        return reward
    assert _r(0.3) - _r(0.0) == pytest.approx(-0.3)


def test_potion_death_penalty_win_unaffected():
    def _win_reward(penalty):
        env = STS2RunEnv(potion_death_penalty=penalty)
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
    assert _win_reward(0.3) == pytest.approx(_win_reward(0.0))


def test_potion_death_penalty_default_off():
    assert STS2RunEnv()._potion_death_penalty == 0.0


from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_v9_flags_reach_run_env():
    spec = EnvSpec(kind="run", rest_heal_shaping_knee_cap=True,
                   potion_death_expiry=True)
    env = build_env(spec)
    assert env._rest_heal_shaping_knee_cap is True
    assert env._potion_death_expiry is True


def test_envspec_potion_death_penalty_reaches_run_env():
    spec = EnvSpec(kind="run", potion_death_penalty=0.3)
    env = build_env(spec)
    assert env._potion_death_penalty == 0.3


def test_envspec_v9_flags_default_off():
    env = build_env(EnvSpec(kind="run"))
    assert env._rest_heal_shaping_knee_cap is False
    assert env._potion_death_expiry is False


# ── v16: energy_waste_penalty — flat -penalty per unspent energy point at
# every player-turn END_TURN. UNCONDITIONAL by design (empty-hand turns
# charge too: that is the deck-building gradient, and no alternative
# action exists on those turns so it cannot distort combat play).
# Tiebreaker-sized (0.02) so passing vs Thorns/Prism-class punishers
# stays strictly optimal — HP shaping charges ~an order of magnitude
# more per HP than this charges per energy.


def _end_turn_step(env, energy):
    """One step() whose pending request is a player-turn END_TURN with
    `energy` unspent. _count_behavior stays REAL — the reward reads the
    counter delta it produces."""
    env._request = SimpleNamespace(
        kind=DecisionKind.COMBAT,
        combat=SimpleNamespace(
            phase=Phase.PLAYER_TURN,
            room_type=None,
            player=SimpleNamespace(energy=energy)))
    env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
    env._translate = lambda action, request: 0   # answer 0 == END_TURN
    env._switch = lambda a: None
    env._info = lambda: {}
    return env.step(0)


def _end_turn_reward(penalty, energy):
    env = STS2RunEnv(energy_waste_penalty=penalty)
    env.reset(seed=0)
    _, reward, *_ = _end_turn_step(env, energy)
    return reward


def test_energy_waste_penalty_charges_per_unspent_point():
    assert (_end_turn_reward(0.02, 3) - _end_turn_reward(0.0, 3)
            == pytest.approx(-0.06))


def test_energy_waste_penalty_zero_energy_free():
    assert (_end_turn_reward(0.02, 0) - _end_turn_reward(0.0, 0)
            == pytest.approx(0.0))


def test_energy_waste_penalty_not_charged_outside_player_turn():
    def _r(penalty):
        env = STS2RunEnv(energy_waste_penalty=penalty)
        env.reset(seed=0)
        env._request = SimpleNamespace(
            kind=DecisionKind.COMBAT,
            combat=SimpleNamespace(
                phase=Phase.COMBAT_OVER,
                room_type=None,
                player=SimpleNamespace(energy=3)))
        env._build_obs = lambda: {"f": np.zeros(1, np.float32), "i": np.zeros(1, np.int32)}
        env._translate = lambda action, request: 0
        env._switch = lambda a: None
        env._info = lambda: {}
        _, reward, *_ = env.step(0)
        return reward
    assert _r(0.02) == pytest.approx(_r(0.0))


def test_energy_waste_penalty_default_off():
    assert STS2RunEnv()._energy_waste_penalty == 0.0
