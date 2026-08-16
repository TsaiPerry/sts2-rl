"""v11 (plan 2026-08-14-v11-combat-detour Task 2): --reward-boss threading.

The env kwarg lands in Task 1 (`run_env.py` reward_boss); this only threads
it EnvSpec -> build_env -> CLI, same pattern as v10's hp_potential_low_share.
"""
import argparse

from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_reward_boss_reaches_run_env():
    env = build_env(EnvSpec(kind="run", reward_boss=3.0))
    assert env._reward_boss == 3.0


def test_envspec_reward_boss_default_bit_identical():
    # 0.0 is the env's own default -- a default spec must build the same env.
    assert build_env(EnvSpec(kind="run"))._reward_boss == 0.0


def test_env_spec_threads_reward_boss():
    import train_torch
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            reward_boss=3.0)
    assert train_torch.env_spec(ns).reward_boss == 3.0
