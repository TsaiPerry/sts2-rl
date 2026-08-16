"""v10 (plan 2026-08-13-v10-escape-and-settle Task 1): --hp-potential-low-share.

The env kwarg has existed since v8 (`run_env.py` `_hp_potential`); v10 only
threads it EnvSpec -> build_env -> CLI so the s11-lowshare contingency rung
(0.7 -> 0.8, steeper danger zone) is a script-arg edit, not a code change.
"""
import argparse

from sts2_rl.vec_env import EnvSpec, build_env


def test_envspec_low_share_reaches_run_env():
    env = build_env(EnvSpec(kind="run", hp_potential_low_share=0.8))
    assert env._hp_potential_low_share == 0.8


def test_envspec_low_share_default_bit_identical():
    # 0.7 is the env's own default -- a default spec must build the same env.
    assert build_env(EnvSpec(kind="run"))._hp_potential_low_share == 0.7


def test_env_spec_threads_low_share():
    import train_torch
    ns = argparse.Namespace(env="run", acts=None, card_obs="hybrid",
                            encounter=None, enemy_hp_reward=0.0,
                            win_hp_bonus=0.0, branch_prob=0.0,
                            hp_potential_low_share=0.8)
    assert train_torch.env_spec(ns).hp_potential_low_share == 0.8
