import numpy as np
from sts2_rl.vec_env import EnvSpec, SerialVecEnv, build_env


def test_stepbatch_carries_per_env_reward_anneal():
    spec = EnvSpec(kind="run",
                   floor_rewards_by_act=(1.0, 1.5, 2.0),
                   reward_win_run=3.0,
                   elite_rewards_by_act=(2.0, 3.0, 4.0),
                   reward_boss=3.0)
    envs = SerialVecEnv(spec, n_envs=2)
    envs.reset([11, 12])
    for _ in range(50):
        batch = envs.step([0, 0])   # action 0 each env (illegal -> no-op is fine)
        assert batch.reward_anneal.shape == (2,)
        assert batch.reward_anneal.dtype == np.float32
        assert np.all(np.isfinite(batch.reward_anneal))


def test_env_spec_progress_scale_reaches_env():
    spec = EnvSpec(kind="run", progress_potential_scale=2.5)
    env = build_env(spec)
    assert env._progress_potential_scale == 2.5


def test_env_spec_progress_scale_defaults_off():
    assert EnvSpec(kind="run").progress_potential_scale == 0.0
    assert build_env(EnvSpec(kind="run"))._progress_potential_scale == 0.0
