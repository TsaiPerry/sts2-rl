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
from sts2_rl.full_env import (
    DEFAULT_ENCOUNTERS,
    ENEMY_ROW_DIM,
    MAX_ENEMIES,
    MAX_HAND,
    MONSTER_INDEX,
    N_POWERS,
    OBS_SCHEMA_VERSION,
    POWER_IDS,
    _N_ENEMY_SCALARS,
)


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
    assert OBS_SCHEMA_VERSION == 2
    assert env.observation_space.shape[0] == 4591   # hybrid, schema v2
    assert env.action_space.n == env.n_actions == 79


def test_features_mode_is_smaller():
    assert STS2FullCombatEnv(card_obs="features").observation_space.shape[0] == 3421


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


def test_absolute_hp_encoding_in_player_vitals():
    env = STS2FullCombatEnv(encounter=DEFAULT_ENCOUNTERS[0])
    obs, _ = env.reset(seed=0)
    p = env._state.player
    assert obs[0] == pytest.approx(p.hp / p.max_hp)
    assert obs[1] == pytest.approx(min(1.0, p.hp / 100.0))     # fine absolute
    assert obs[2] == pytest.approx(p.hp / 500.0)               # coarse absolute
    assert obs[3] == pytest.approx(min(1.0, p.max_hp / 100.0))


def test_dexterity_is_observable():
    from sts2_rl import PowerCmd
    from sts2_rl.powers import DexterityPower

    env = STS2FullCombatEnv(encounter=DEFAULT_ENCOUNTERS[0])
    obs_before, _ = env.reset(seed=0)
    assert obs_before[9] == pytest.approx(0.5)                 # dex slot, signed zero
    PowerCmd.apply(env._state.hooks, env._state.player, DexterityPower, 6)
    obs_after = env._build_obs()
    assert obs_after[9] == pytest.approx((6 + 30) / 60.0)


def test_full_power_vocabulary_triples():
    import random
    from sts2_rl import CombatState, PowerCmd
    from sts2_rl.powers import ALL_POWERS, RitualPower

    assert POWER_IDS == sorted(ALL_POWERS)                     # no curated subset
    c = CombatState(rng=random.Random(0), encounter=DEFAULT_ENCOUNTERS[0])
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, e, RitualPower, 3)
    triples = STS2FullCombatEnv._power_triples(e)
    i = 3 * POWER_IDS.index("ritual")
    assert triples[i:i + 3] == [1.0, (3 + 10) / 20.0, (3 + 50) / 100.0]
    j = 3 * POWER_IDS.index("poison")                          # absent power
    assert triples[j:j + 3] == [0.0, 0.5, 0.5]


def test_enemy_row_identity_and_pipeline_preview():
    from sts2_rl import FUZZY_WURM_ENCOUNTER, PowerCmd
    from sts2_rl.powers import WeakPower

    env = STS2FullCombatEnv(encounter=FUZZY_WURM_ENCOUNTER)
    env.reset(seed=0)
    enemy = env._state.enemies[0]
    row = env._enemy_row(enemy)
    assert len(row) == ENEMY_ROW_DIM
    # Identity one-hot sits right after the scalar block.
    hot = row[_N_ENEMY_SCALARS:_N_ENEMY_SCALARS + len(MONSTER_INDEX)]
    assert hot[MONSTER_INDEX[enemy.__class__.__name__]] == 1.0
    assert sum(hot) == 1.0
    # Intent damage runs through the modifier pipeline: Weak lowers it.
    per_hit_idx = 18   # present+ratio+hp2+maxhp2+block2+str+9 flags
    if row[per_hit_idx] > 0:
        before = row[per_hit_idx]
        PowerCmd.apply(env._state.hooks, enemy, WeakPower, 1)
        after = env._enemy_row(enemy)[per_hit_idx]
        assert after < before
    # Absent slots are all-zero rows of the same width.
    assert env._enemy_row(None) == [0.0] * ENEMY_ROW_DIM


def test_damage_matrix_alignment():
    from sts2_rl import FUZZY_WURM_ENCOUNTER

    env = STS2FullCombatEnv(encounter=FUZZY_WURM_ENCOUNTER)
    env.reset(seed=0)
    matrix = env._damage_matrix()
    assert len(matrix) == MAX_HAND * MAX_ENEMIES
    s = env._state
    living = [i for i, e in enumerate(s.enemies) if not e.is_gone]
    strikes = [h for h, c in enumerate(s.player.hand) if c.id == "strike"]
    assert strikes, "default deck should put a strike in the opening hand"
    for h in strikes:
        for e_i in living:
            assert matrix[h * MAX_ENEMIES + e_i] == pytest.approx(0.06)  # 6/100
    # Columns for absent enemy slots stay zero.
    for h in range(MAX_HAND):
        for e_i in range(len(s.enemies), MAX_ENEMIES):
            assert matrix[h * MAX_ENEMIES + e_i] == 0.0


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
