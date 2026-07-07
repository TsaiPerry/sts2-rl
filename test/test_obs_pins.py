"""Observation pin tests — OBS_PLAN Phase 4, step 10.

Constructed combats with fixed RNG asserting EXACT feature values through the
full observation vector, addressed by the named layout map (full_env.obs_slices)
instead of magic indices: player vitals, pipeline-accurate intent previews
(Weak / Vulnerable / block absorption / multi-hit), card numbers, the damage
matrix under Strength/Vulnerable, pile histograms, and the numeric-ablation
wrapper. Enemies are fixed-stat probe dummies so every expected number is
hand-computable.

Run with:  py -m pytest test/test_obs_pins.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from sts2_rl import (
    BlockCmd,
    DexterityPower,
    Encounter,
    PowerCmd,
    StrengthPower,
    STS2FullCombatEnv,
    VulnerablePower,
    WeakPower,
)
from sts2_rl.full_env import (
    AblatedObsEnv,
    CARD_INDEX,
    MAX_ENEMIES,
    N_CARDS,
    numeric_obs_indices,
    obs_segments,
    obs_slices,
)
from sts2_rl.probes import probe_dummy


def _pin_env(hp: int = 20, damage: int = 12, hits: int = 1) -> STS2FullCombatEnv:
    """A one-dummy combat with hand = [Strike, Defend] and no randomness in
    the enemy's stats, so every observation value is hand-computable."""
    dummy = probe_dummy("PinDummy", hp=hp, damage=damage, hits=hits)
    env = STS2FullCombatEnv(
        encounter=Encounter(id="pin", monster_classes=[dummy]),
        deck=["strike", "defend"],
    )
    env.reset(seed=0)
    return env


def _hand_slot(env: STS2FullCombatEnv, card_id: str) -> int:
    return next(i for i, c in enumerate(env._state.player.hand) if c.id == card_id)


# ── Layout map ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["hybrid", "features"])
def test_layout_covers_obs_exactly(mode):
    env = STS2FullCombatEnv(card_obs=mode)
    dim = env.observation_space.shape[0]
    segs = obs_segments(mode)
    assert sum(w for _, w in segs) == dim
    sl = obs_slices(mode)
    assert len(sl) == len(segs)               # names are unique
    pos = 0
    for name, width in segs:                  # contiguous, in declaration order
        assert sl[name] == slice(pos, pos + width)
        pos += width
    assert pos == dim


def test_layout_landmarks():
    from sts2_rl import FUZZY_WURM_ENCOUNTER
    from sts2_rl.full_env import MONSTER_INDEX

    sl = obs_slices()
    # The dedicated dexterity slot is the documented obs[9].
    assert sl["player.dexterity"] == slice(9, 10)

    env = STS2FullCombatEnv(encounter=FUZZY_WURM_ENCOUNTER)
    obs, _ = env.reset(seed=0)
    # The damage-matrix slice is exactly _damage_matrix's output.
    np.testing.assert_allclose(obs[sl["damage_matrix"]], env._damage_matrix(), rtol=1e-6)
    # Enemy identity one-hot lands where the layout says it does.
    hot = obs[sl["enemy0.identity"]]
    assert hot[MONSTER_INDEX[env._state.enemies[0].__class__.__name__]] == 1.0
    assert hot.sum() == 1.0
    # Hand-slot one-hot likewise.
    hot0 = obs[sl["hand0.onehot"]]
    assert hot0[CARD_INDEX[env._state.player.hand[0].id]] == 1.0
    assert hot0.sum() == 1.0


# ── Player vitals ─────────────────────────────────────────────────────────────


def test_player_vitals_pins():
    env = _pin_env(hp=20, damage=12)
    s = env._state
    s.player.hp = 12
    s.player.energy = 1
    sl = obs_slices()
    obs = env._build_obs()
    assert obs[sl["player.hp_ratio"]][0] == pytest.approx(12 / 80)
    np.testing.assert_allclose(obs[sl["player.hp_abs"]], [0.12, 0.024], rtol=1e-6)
    np.testing.assert_allclose(obs[sl["player.max_hp_abs"]], [0.80, 0.16], rtol=1e-6)
    np.testing.assert_allclose(obs[sl["player.block_abs"]], [0.0, 0.0])
    assert obs[sl["player.energy"]][0] == pytest.approx(0.1)
    assert obs[sl["player.turn"]][0] == pytest.approx(1 / 30)
    # 12 telegraphed, no block: the end-turn decision number is 12.
    np.testing.assert_allclose(obs[sl["player.incoming_post_block"]], [0.12, 0.024], rtol=1e-6)


# ── Intent previews through the modifier pipeline ─────────────────────────────


def test_incoming_preview_pins():
    env = _pin_env(hp=20, damage=15)
    s = env._state
    sl = obs_slices()
    # Layout: per_hit/100, hits/10, total/100, total/500, post_block/100, /500.
    obs = env._build_obs()
    np.testing.assert_allclose(
        obs[sl["enemy0.intent_preview"]], [0.15, 0.1, 0.15, 0.03, 0.15, 0.03], rtol=1e-6
    )
    # Weak on the enemy: int(15 × 0.75) = 11 — the number the game displays.
    PowerCmd.apply(s.hooks, s.enemies[0], WeakPower, 1)
    obs = env._build_obs()
    np.testing.assert_allclose(
        obs[sl["enemy0.intent_preview"]], [0.11, 0.1, 0.11, 0.022, 0.11, 0.022], rtol=1e-6
    )
    # Block absorbs: post-block 11 − 4 = 7; the pre-block display is unchanged.
    BlockCmd.apply(s.hooks, s.player, 4)
    obs = env._build_obs()
    np.testing.assert_allclose(
        obs[sl["enemy0.intent_preview"]], [0.11, 0.1, 0.11, 0.022, 0.07, 0.014], rtol=1e-6
    )
    np.testing.assert_allclose(obs[sl["player.incoming_post_block"]], [0.07, 0.014], rtol=1e-6)
    # Vulnerable on the player multiplies in: int(15 × 0.75 × 1.5) = 16.
    PowerCmd.apply(s.hooks, s.player, VulnerablePower, 1)
    obs = env._build_obs()
    assert obs[sl["enemy0.intent_preview"]][0] == pytest.approx(0.16)


def test_multi_hit_post_block_pins():
    env = _pin_env(hp=20, damage=6, hits=2)
    s = env._state
    sl = obs_slices()
    obs = env._build_obs()
    np.testing.assert_allclose(
        obs[sl["enemy0.intent_preview"]], [0.06, 0.2, 0.12, 0.024, 0.12, 0.024], rtol=1e-6
    )
    # 4 block absorbs hit by hit: lose (6−4) + 6 = 8, not 12 − 4 applied once.
    BlockCmd.apply(s.hooks, s.player, 4)
    obs = env._build_obs()
    np.testing.assert_allclose(obs[sl["enemy0.intent_preview"]][4:], [0.08, 0.016], rtol=1e-6)


def test_preview_equals_hp_actually_lost():
    env = _pin_env(hp=20, damage=12)
    s = env._state
    s.player.hp = 30
    sl = obs_slices()
    obs = env._build_obs()
    np.testing.assert_allclose(obs[sl["player.incoming_post_block"]], [0.12, 0.024], rtol=1e-6)
    env.step(0)                                # end turn with no plays
    assert s.player.hp == 18                   # preview == reality


# ── Card numbers and the damage matrix ────────────────────────────────────────


def test_card_number_pins():
    env = _pin_env()
    sl = obs_slices()
    obs = env._build_obs()
    # numbers layout: dmg/100, dmg/500, hits/10, block/100, eff_block/100,
    # hp_loss/100, magic/20.
    strike, defend = _hand_slot(env, "strike"), _hand_slot(env, "defend")
    np.testing.assert_allclose(
        obs[sl[f"hand{strike}.numbers"]], [0.06, 0.012, 0.1, 0, 0, 0, 0], rtol=1e-6
    )
    np.testing.assert_allclose(
        obs[sl[f"hand{defend}.numbers"]], [0, 0, 0.1, 0.05, 0.05, 0, 0], rtol=1e-6
    )
    # Dexterity moves the effective block, not the printed base.
    PowerCmd.apply(env._state.hooks, env._state.player, DexterityPower, 2)
    obs = env._build_obs()
    np.testing.assert_allclose(
        obs[sl[f"hand{defend}.numbers"]], [0, 0, 0.1, 0.05, 0.07, 0, 0], rtol=1e-6
    )


def test_damage_matrix_pins_strength_and_vulnerable():
    env = _pin_env()
    s = env._state
    sl = obs_slices()
    cell = sl["damage_matrix"].start + _hand_slot(env, "strike") * MAX_ENEMIES
    assert env._build_obs()[cell] == pytest.approx(0.06)
    # Strength is additive before Vulnerable multiplies: (6+3) → int(9×1.5) = 13.
    PowerCmd.apply(s.hooks, s.player, StrengthPower, 3)
    assert env._build_obs()[cell] == pytest.approx(0.09)
    PowerCmd.apply(s.hooks, s.enemies[0], VulnerablePower, 1)
    assert env._build_obs()[cell] == pytest.approx(0.13)


def test_pile_histograms_pin_played_cards():
    env = _pin_env()
    s = env._state
    sl = obs_slices()
    obs = env._build_obs()
    for pile in ("draw_pile", "discard_pile", "exhaust_pile"):
        assert not obs[sl[pile]].any()         # 2-card deck: everything is in hand
    h = _hand_slot(env, "strike")
    s.player.hand[h].upgrade()
    obs, *_ = env.step(1 + h * MAX_ENEMIES)    # play the Strike+ at enemy 0
    hist = obs[sl["discard_pile"]]
    assert hist[N_CARDS + CARD_INDEX["strike"]] == pytest.approx(0.1)   # upgraded half
    assert hist.sum() == pytest.approx(0.1)    # nothing else, nothing in the base half


# ── Numeric ablation ──────────────────────────────────────────────────────────


def test_numeric_indices_cover_the_preview_segments():
    sl = obs_slices()
    idx = set(numeric_obs_indices().tolist())
    for name in ("player.hp_abs", "player.max_hp_abs", "player.block_abs",
                 "player.incoming_post_block", "hand0.numbers",
                 "enemy0.hp_abs", "enemy0.intent_preview", "damage_matrix"):
        span = set(range(sl[name].start, sl[name].stop))
        assert span <= idx, name
    for name in ("player.hp_ratio", "player.energy", "player.powers",
                 "hand0.onehot", "hand0.features", "enemy0.intent_flags",
                 "enemy0.identity", "draw_pile"):
        span = set(range(sl[name].start, sl[name].stop))
        assert not (span & idx), name


def test_ablation_wrapper_zeroes_only_numeric_dims():
    idx = numeric_obs_indices()
    raw = STS2FullCombatEnv()
    wrapped = AblatedObsEnv(STS2FullCombatEnv())
    assert wrapped.observation_space.shape == raw.observation_space.shape
    obs_raw, _ = raw.reset(seed=5)
    obs_abl, _ = wrapped.reset(seed=5)
    assert np.all(obs_abl[idx] == 0.0)
    keep = np.setdiff1d(np.arange(obs_raw.shape[0]), idx)
    np.testing.assert_array_equal(obs_abl[keep], obs_raw[keep])
    # Dynamics and masks are untouched — only the observation is impoverished.
    np.testing.assert_array_equal(wrapped.action_masks(), raw.action_masks())
