"""v24 per-act elite pay: `elite_rewards_by_act` /
`elite_attempt_rewards_by_act` replace the flat `reward_elite` /
`reward_elite_attempt` scalars, indexed by the run's 0-based `act_index`,
mirroring `floor_rewards_by_act`. Default OFF: unset tuples must leave the
flat scalars exactly as they were.

Scripted the same way as the v11 reward tests: monkeypatch
`_translate`/`_count_behavior`/`_switch` so one step() is driven by the test.
"""
import pytest

from sts2_rl.run_env import STS2RunEnv


def _scripted_step(env, mutate):
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = mutate
    return env.step(0)


def _win_elite_in_act(env, act_index):
    """Drive one step in which exactly one elite WIN is tallied in `act`."""
    env.reset(seed=0)
    env._run.act_index = act_index

    def _mutate(answer):
        env._ep_elites_won += 1

    return _scripted_step(env, _mutate)[1]


def _enter_elite_in_act(env, act_index):
    env.reset(seed=0)
    env._run.act_index = act_index

    def _mutate(answer):
        env._ep_elites_fought += 1

    return _scripted_step(env, _mutate)[1]


def test_default_kwargs_inert():
    env = STS2RunEnv()
    assert env._elite_rewards_by_act is None
    assert env._elite_attempt_rewards_by_act is None


def test_flat_scalar_still_used_when_tuples_unset():
    env = STS2RunEnv(reward_elite=2.0)
    for act in (0, 1, 2):
        assert _win_elite_in_act(env, act) == pytest.approx(2.0)


def test_elite_win_pay_scales_by_act():
    env = STS2RunEnv(reward_elite=2.0, elite_rewards_by_act=(2.0, 3.0, 4.0))
    assert _win_elite_in_act(env, 0) == pytest.approx(2.0)
    assert _win_elite_in_act(env, 1) == pytest.approx(3.0)
    assert _win_elite_in_act(env, 2) == pytest.approx(4.0)


def test_elite_attempt_pay_scales_by_act():
    env = STS2RunEnv(reward_elite_attempt=1.0,
                     elite_attempt_rewards_by_act=(1.0, 1.5, 2.0))
    assert _enter_elite_in_act(env, 0) == pytest.approx(1.0)
    assert _enter_elite_in_act(env, 1) == pytest.approx(1.5)
    assert _enter_elite_in_act(env, 2) == pytest.approx(2.0)


def test_by_act_tuple_overrides_the_flat_scalar():
    """The tuple REPLACES the scalar -- they must not both pay."""
    env = STS2RunEnv(reward_elite=99.0, elite_rewards_by_act=(2.0, 3.0, 4.0))
    assert _win_elite_in_act(env, 1) == pytest.approx(3.0)


def test_act_index_past_the_tuple_clamps_to_last_act():
    """Same clamp the floor-reward line uses -- never an IndexError."""
    env = STS2RunEnv(reward_elite=2.0, elite_rewards_by_act=(2.0, 3.0, 4.0))
    assert _win_elite_in_act(env, 7) == pytest.approx(4.0)


def test_win_and_attempt_are_independent_terms():
    """A won elite in act 3 pays BOTH per-act rates (entry + win)."""
    env = STS2RunEnv(reward_elite=2.0, reward_elite_attempt=1.0,
                     elite_rewards_by_act=(2.0, 3.0, 4.0),
                     elite_attempt_rewards_by_act=(1.0, 1.5, 2.0))
    env.reset(seed=0)
    env._run.act_index = 2

    def _mutate(answer):
        env._ep_elites_won += 1
        env._ep_elites_fought += 1

    assert _scripted_step(env, _mutate)[1] == pytest.approx(6.0)
