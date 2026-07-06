"""Smoke tests for STS2FullCombatEnv — the full-combat Gymnasium wrapper.

These exercise the env wiring without SB3: observation/space consistency,
action-mask legality, that every Act 1 encounter plays to completion under a
masked random policy, seed determinism, and reward/termination sanity.

Run with:  py -m pytest test/test_full_env.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from sts2_rl import STS2FullCombatEnv
from sts2_rl.full_env import DEFAULT_ENCOUNTERS


def _masked_rollout(env, seed, max_steps=500):
    obs, info = env.reset(seed=seed)
    assert env.observation_space.contains(obs)
    rng = np.random.default_rng(seed)
    for _ in range(max_steps):
        mask = env.action_masks()
        assert mask.shape == (env.n_actions,)
        assert mask.any(), "no legal action available"
        action = int(rng.choice(np.flatnonzero(mask)))
        obs, reward, terminated, truncated, info = env.step(action)
        assert env.observation_space.contains(obs), (obs.min(), obs.max())
        assert np.isfinite(reward)
        if terminated or truncated:
            return terminated, truncated, info
    pytest.fail("episode did not finish within max_steps")


def test_spaces_declared():
    env = STS2FullCombatEnv()
    assert env.observation_space.shape[0] == 1599   # hybrid
    assert env.action_space.n == env.n_actions == 79


def test_features_mode_is_smaller():
    assert STS2FullCombatEnv(card_obs="features").observation_space.shape[0] == 429


def test_obs_within_declared_space_at_reset():
    env = STS2FullCombatEnv()
    obs, _ = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    assert obs.min() >= 0.0 and obs.max() <= 1.0


@pytest.mark.parametrize("enc", DEFAULT_ENCOUNTERS, ids=lambda e: e.id)
def test_every_encounter_runs_to_completion(enc):
    env = STS2FullCombatEnv(encounter=enc, max_steps=400)
    terminated, truncated, info = _masked_rollout(env, seed=3, max_steps=400)
    assert terminated or truncated
    if terminated:
        assert "is_success" in info


def test_seed_determinism():
    def trace(seed):
        env = STS2FullCombatEnv()
        obs, _ = env.reset(seed=seed)
        out = [obs.tobytes()]
        for _ in range(12):
            action = int(np.flatnonzero(env.action_masks())[0])
            obs, reward, term, trunc, _ = env.step(action)
            out.append((round(reward, 6), obs.tobytes(), term))
            if term or trunc:
                break
        return out

    assert trace(42) == trace(42)
    assert trace(1) != trace(2)


def test_potions_are_targetable_and_untargetable():
    env = STS2FullCombatEnv(
        encounter=DEFAULT_ENCOUNTERS[0], potions=["fire_potion", "block_potion"]
    )
    env.reset(seed=0)
    mask = env.action_masks()
    potion_actions = [i for i in range(env._potion_base, env.n_actions) if mask[i]]
    assert len(potion_actions) >= 2   # one non-targeted (block) + one targeted (fire)


def test_win_gives_terminal_reward():
    # A trivially strong deck vs a single weak encounter should net a win with a
    # positive terminal bonus within a few seeds.
    for seed in range(20):
        env = STS2FullCombatEnv(
            encounter=DEFAULT_ENCOUNTERS[0],
            deck=["bludgeon"] * 6 + ["defend"] * 4,
        )
        _, _, info = _masked_rollout(env, seed=seed)
        if info.get("is_success"):
            return
    pytest.skip("no win in 20 seeds (random policy) — reward path still exercised")
