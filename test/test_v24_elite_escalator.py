"""v24: within-act elite escalator. The N-th elite KILLED in an act pays
base * (1 + esc * (N-1)); the counter resets when act_index advances;
attempt pay is NOT escalated; default 0.0 = bit-identical.

Scripted the same way as test_v24_elite_by_act.py: monkeypatch
`_translate`/`_count_behavior`/`_switch` so one step() is driven by the test.
"""
import pytest

from sts2_rl.run_env import STS2RunEnv


def _scripted_step(env, mutate):
    env._translate = lambda action, request: 0
    env._count_behavior = lambda request, answer: None
    env._switch = mutate
    return env.step(0)


def _win_elite(env):
    def _mutate(answer):
        env._ep_elites_won += 1
    return _scripted_step(env, _mutate)[1]


def _enter_elite(env):
    def _mutate(answer):
        env._ep_elites_fought += 1
    return _scripted_step(env, _mutate)[1]


def _win_elite_and_advance_act(env, new_act_index):
    def _mutate(answer):
        env._ep_elites_won += 1
        env._run.act_index = new_act_index
    return _scripted_step(env, _mutate)[1]


def test_escalator_pays_increasing_rate_within_an_act():
    env = STS2RunEnv(reward_elite=2.0, reward_elite_escalator=0.5)
    env.reset(seed=0)
    assert _win_elite(env) == pytest.approx(2.0)
    assert _win_elite(env) == pytest.approx(3.0)
    assert _win_elite(env) == pytest.approx(4.0)


def test_escalator_composes_with_by_act():
    env = STS2RunEnv(reward_elite=2.0, reward_elite_escalator=0.5,
                     elite_rewards_by_act=(2.0, 3.0, 4.0))
    env.reset(seed=0)
    env._run.act_index = 0
    assert _win_elite(env) == pytest.approx(2.0)
    assert _win_elite(env) == pytest.approx(3.0)


def test_act_advance_resets_the_escalator_counter():
    env = STS2RunEnv(reward_elite=2.0, reward_elite_escalator=0.5,
                     elite_rewards_by_act=(2.0, 3.0, 4.0))
    env.reset(seed=0)
    env._run.act_index = 0
    assert _win_elite(env) == pytest.approx(2.0)
    # This kill's own step advances the act (a boss-step kill): it still
    # pays at the OLD act's escalated count (reset happens AFTER the pay),
    # but at the NEW act's base rate since `run.act_index` is post-step.
    assert _win_elite_and_advance_act(env, 1) == pytest.approx(4.5)
    # The counter is now reset -- the next kill in act 1 pays act 1's base.
    assert _win_elite(env) == pytest.approx(3.0)


def test_reset_fires_on_a_no_kill_act_advance():
    """An act advance with NO elite kill in that step (elite_delta == 0,
    e.g. a plain boss step) must still reset the counter -- the next kill
    in the new act pays unescalated."""
    env = STS2RunEnv(reward_elite=2.0, reward_elite_escalator=0.5,
                     elite_rewards_by_act=(2.0, 3.0, 4.0))
    env.reset(seed=0)
    env._run.act_index = 0
    assert _win_elite(env) == pytest.approx(2.0)

    def _advance_no_kill(answer):
        env._run.act_index = 1

    assert _scripted_step(env, _advance_no_kill)[1] == pytest.approx(0.0)
    assert _win_elite(env) == pytest.approx(3.0)


def test_attempt_pay_is_not_escalated():
    env = STS2RunEnv(reward_elite_attempt=1.0, reward_elite_escalator=0.5)
    env.reset(seed=0)
    assert _enter_elite(env) == pytest.approx(1.0)
    assert _enter_elite(env) == pytest.approx(1.0)


def test_default_escalator_is_bit_identical():
    env = STS2RunEnv(reward_elite=2.0)
    env.reset(seed=0)
    assert env._reward_elite_escalator == 0.0
    assert _win_elite(env) == pytest.approx(2.0)
    assert _win_elite(env) == pytest.approx(2.0)
