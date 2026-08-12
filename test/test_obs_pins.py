"""Observation pin tests — OBS_PLAN Phase 4, step 10 (v4 rewrite).

Constructed combats with fixed RNG asserting EXACT feature values through the
v4 observation, addressed by ``combat_obs_layout()``'s named slices (never
magic indices): player vitals, pipeline-accurate intent previews (Weak /
Vulnerable / block absorption / multi-hit), card numbers, the damage matrix
under Strength/Vulnerable, the cards (pile) block, and the numeric-ablation
wrapper. Enemies are fixed-stat probe dummies so every expected number is
hand-computable.

v4 note: the old dense-per-vocab-id float blocks this file addressed by name
(``obs_segments``/``obs_slices``, one-hot hand/enemy identity segments, pile
histograms) no longer exist — see OBS_SCHEMA.md Sec.2/Sec.5. Every test below
still pins the SAME underlying property the v3 version did; only the
addressing changed to combat_obs_layout()'s int/float row blocks. Where a
property is now already pinned by test_combat_obs_v4.py (the reviewed v4
acceptance suite), it is deleted here rather than duplicated — see the
bottom of the file for the accounting.

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
    MAX_HAND,
    N_CARD_FEATURES,
    _N_ENEMY_SCALARS,
    combat_obs_layout,
    numeric_obs_indices,
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


def _enemy0_row(env: STS2FullCombatEnv, layout) -> np.ndarray:
    """Enemy slot 0's 24-float scalar row (``_enemy_floats``'s layout:
    present, hp_ratio, hp×2, max_hp×2, block×2, strength, 9 intent flags,
    then offsets 18-23 = per_hit/100, hits/10, total×2, post_block×2)."""
    return env._build_obs()["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)[0]


# ── Player vitals ─────────────────────────────────────────────────────────────


def test_player_vitals_pins():
    env = _pin_env(hp=20, damage=12)
    s = env._state
    s.player.hp = 12
    s.player.energy = 1
    layout = combat_obs_layout()
    f = env._build_obs()["f"]
    assert f[layout.f_slices["player.hp_ratio"]][0] == pytest.approx(12 / 80)
    np.testing.assert_allclose(f[layout.f_slices["player.hp_abs"]], [0.12, 0.024], rtol=1e-6)
    np.testing.assert_allclose(f[layout.f_slices["player.max_hp_abs"]], [0.80, 0.16], rtol=1e-6)
    np.testing.assert_allclose(f[layout.f_slices["player.block_abs"]], [0.0, 0.0])
    assert f[layout.f_slices["player.energy"]][0] == pytest.approx(0.1)
    assert f[layout.f_slices["player.turn"]][0] == pytest.approx(1 / 30)
    # 12 telegraphed, no block: the end-turn decision number is 12.
    np.testing.assert_allclose(
        f[layout.f_slices["player.incoming_post_block"]], [0.12, 0.024], rtol=1e-6)


# ── Intent previews through the modifier pipeline ─────────────────────────────


def test_incoming_preview_pins():
    env = _pin_env(hp=20, damage=15)
    s = env._state
    layout = combat_obs_layout()
    row = _enemy0_row(env, layout)
    np.testing.assert_allclose(row[18:24], [0.15, 0.1, 0.15, 0.03, 0.15, 0.03], rtol=1e-6)
    # Weak on the enemy: int(15 × 0.75) = 11 — the number the game displays.
    PowerCmd.apply(s.hooks, s.enemies[0], WeakPower, 1)
    row = _enemy0_row(env, layout)
    np.testing.assert_allclose(row[18:24], [0.11, 0.1, 0.11, 0.022, 0.11, 0.022], rtol=1e-6)
    # Block absorbs: post-block 11 − 4 = 7; the pre-block display is unchanged.
    BlockCmd.apply(s.hooks, s.player, 4)
    row = _enemy0_row(env, layout)
    np.testing.assert_allclose(row[18:24], [0.11, 0.1, 0.11, 0.022, 0.07, 0.014], rtol=1e-6)
    f = env._build_obs()["f"]
    np.testing.assert_allclose(
        f[layout.f_slices["player.incoming_post_block"]], [0.07, 0.014], rtol=1e-6)
    # Vulnerable on the player multiplies in: int(15 × 0.75 × 1.5) = 16.
    PowerCmd.apply(s.hooks, s.player, VulnerablePower, 1)
    row = _enemy0_row(env, layout)
    assert row[18] == pytest.approx(0.16)


def test_multi_hit_post_block_pins():
    env = _pin_env(hp=20, damage=6, hits=2)
    s = env._state
    layout = combat_obs_layout()
    row = _enemy0_row(env, layout)
    np.testing.assert_allclose(row[18:24], [0.06, 0.2, 0.12, 0.024, 0.12, 0.024], rtol=1e-6)
    # 4 block absorbs hit by hit: lose (6−4) + 6 = 8, not 12 − 4 applied once.
    BlockCmd.apply(s.hooks, s.player, 4)
    row = _enemy0_row(env, layout)
    np.testing.assert_allclose(row[22:24], [0.08, 0.016], rtol=1e-6)


def test_preview_equals_hp_actually_lost():
    env = _pin_env(hp=20, damage=12)
    s = env._state
    s.player.hp = 30
    layout = combat_obs_layout()
    f = env._build_obs()["f"]
    np.testing.assert_allclose(
        f[layout.f_slices["player.incoming_post_block"]], [0.12, 0.024], rtol=1e-6)
    env.step(0)                                # end turn with no plays
    assert s.player.hp == 18                   # preview == reality


# ── Card numbers and the damage matrix ────────────────────────────────────────


def test_card_number_pins():
    env = _pin_env()
    layout = combat_obs_layout()
    hand_f = env._build_obs()["f"][layout.f_slices["hand.f"]].reshape(-1, N_CARD_FEATURES)
    # Numeric offsets 17-23 within a hand row: dmg/100, dmg/500, hits/10,
    # block/100, eff_block/100, hp_loss/100, magic/20.
    strike, defend = _hand_slot(env, "strike"), _hand_slot(env, "defend")
    np.testing.assert_allclose(hand_f[strike][17:24], [0.06, 0.012, 0.1, 0, 0, 0, 0], rtol=1e-6)
    np.testing.assert_allclose(hand_f[defend][17:24], [0, 0, 0.1, 0.05, 0.05, 0, 0], rtol=1e-6)
    # Obs-parity fix (89U diff vs a live game dump): field 21 (eff_block)
    # must NOT move with Dexterity (or Frail) — the game's own
    # DecisionDumper (SpireBot's CombatObsWriter.cs:470) captures this field
    # via `Hook.ModifyBlock(..., default, card, null, ...)`, and
    # `default(ValueProp)` carries no `.Move` flag, so every block modifier
    # gated on `IsPoweredCardOrMonsterMoveBlock()` (Dexterity's
    # ModifyBlockAdditive, Frail's ModifyBlockMultiplicative, ...) is a
    # no-op for that specific field. See `preview_card_block`'s docstring
    # (sts2_rl/previews.py) and `card_features`'s field-21 comment
    # (sts2_rl/full_env.py). Previously this test pinned the OLD (fully
    # hook-modified) behavior — 0.07 — which is exactly the bug the diff
    # found: 224 hand.f field-21 mismatches, sim showing a Dexterity/Frail-
    # adjusted value where the live game dump showed the raw base block.
    PowerCmd.apply(env._state.hooks, env._state.player, DexterityPower, 2)
    hand_f = env._build_obs()["f"][layout.f_slices["hand.f"]].reshape(-1, N_CARD_FEATURES)
    np.testing.assert_allclose(hand_f[defend][17:24], [0, 0, 0.1, 0.05, 0.05, 0, 0], rtol=1e-6)


def test_damage_matrix_pins_strength_and_vulnerable():
    env = _pin_env()
    s = env._state
    layout = combat_obs_layout()
    cell = _hand_slot(env, "strike") * MAX_ENEMIES     # enemy 0
    dm_slice = layout.f_slices["damage_matrix"]

    def dm() -> float:
        return env._build_obs()["f"][dm_slice][cell]

    assert dm() == pytest.approx(0.06)
    # Strength is additive before Vulnerable multiplies: (6+3) x 1.5 = 13.5.
    # Round-6 obs-parity fix: the game's own preview pipeline (decimal
    # arithmetic, Hook.cs:2511-2539) never truncates mid-pipeline — only its
    # UI text call does, a call site this observation doesn't reach — so
    # damage_matrix keeps the fractional 13.5, not int(9x1.5) == 13 (see
    # previews.py's `_modified_damage` docstring).
    PowerCmd.apply(s.hooks, s.player, StrengthPower, 3)
    assert dm() == pytest.approx(0.09)
    PowerCmd.apply(s.hooks, s.enemies[0], VulnerablePower, 1)
    assert dm() == pytest.approx(0.135)


def test_cards_block_pins_a_played_cards_pile_and_identity():
    """v3 pinned this via a ``2 * N_CARDS``-wide pile histogram
    (``obs[sl["discard_pile"]]``); v4 has no histogram segment at all — the
    property it protected ("the observation describes which pile a played
    card ends up in, and its identity/upgrade level") now lives in the
    sparse, sorted ``cards.ids``/``cards.f`` block instead. This pins that
    same property through the new addressing."""
    env = _pin_env()
    s = env._state
    layout = combat_obs_layout()
    obs = env._build_obs()
    ids = obs["i"][layout.i_slices["cards.ids"]].reshape(-1, 4)
    assert not np.any(ids), "2-card deck: everything is in hand, no pile rows yet"

    h = _hand_slot(env, "strike")
    s.player.hand[h].upgrade()
    obs, *_ = env.step(1 + h * MAX_ENEMIES)    # play the Strike+ at enemy 0
    ids = obs["i"][layout.i_slices["cards.ids"]].reshape(-1, 4)
    fs = obs["f"][layout.f_slices["cards.f"]].reshape(-1, 4)
    present = [r for r in range(len(ids)) if ids[r][0] != 0]
    assert len(present) == 1, "the played Strike+ is the only card off the hand now"
    row = present[0]
    pile_id, card_id, aff_id, ench_id = (int(x) for x in ids[row])
    upgrade, effective_cost, aff_amount, exhaust_next = fs[row]
    assert pile_id == 2                                     # discard
    assert card_id == CARD_INDEX["strike"] + 1
    assert aff_id == 0 and ench_id == 0
    assert upgrade == pytest.approx(1 / 5.0)                # upgrade_level / 5.0
    assert aff_amount == 0.0 and exhaust_next == 0.0


# ── Numeric ablation ──────────────────────────────────────────────────────────


def test_numeric_indices_cover_the_preview_segments_and_exclude_categorical_ones():
    layout = combat_obs_layout()
    idx = set(numeric_obs_indices().tolist())

    def span(name: str) -> set[int]:
        sl = layout.f_slices[name]
        return set(range(sl.start, sl.stop))

    for name in ("player.hp_abs", "player.max_hp_abs", "player.block_abs",
                 "player.incoming_post_block", "damage_matrix"):
        assert span(name) <= idx, name
    for name in ("player.hp_ratio", "player.energy", "player.powers.f"):
        assert not (span(name) & idx), name

    hand_sl = layout.f_slices["hand.f"]
    for h in range(MAX_HAND):
        base = hand_sl.start + h * N_CARD_FEATURES
        numeric = {base + o for o in range(17, 24)}          # dmg..magic
        categorical = {base + o for o in range(2, 12)}        # card/target type onehots
        assert numeric <= idx
        assert not (categorical & idx)

    enemies_sl = layout.f_slices["enemies.f"]
    for e in range(MAX_ENEMIES):
        base = enemies_sl.start + e * _N_ENEMY_SCALARS
        numeric = {base + o for o in (2, 3, 4, 5, 6, 7, 18, 19, 20, 21, 22, 23)}
        categorical = {base + o for o in range(9, 18)}        # 9 intent flags
        assert numeric <= idx
        assert not (categorical & idx)


def test_ablation_wrapper_zeroes_only_numeric_dims_and_never_touches_ids():
    idx = numeric_obs_indices()
    raw = STS2FullCombatEnv()
    wrapped = AblatedObsEnv(STS2FullCombatEnv())
    assert wrapped.observation_space["f"].shape == raw.observation_space["f"].shape
    assert wrapped.observation_space["i"].shape == raw.observation_space["i"].shape
    obs_raw, _ = raw.reset(seed=5)
    obs_abl, _ = wrapped.reset(seed=5)
    assert np.all(obs_abl["f"][idx] == 0.0)
    keep = np.setdiff1d(np.arange(obs_raw["f"].shape[0]), idx)
    np.testing.assert_array_equal(obs_abl["f"][keep], obs_raw["f"][keep])
    # The int half (categorical ids) is never a candidate for ablation at
    # all — only "f" is numeric.
    np.testing.assert_array_equal(obs_abl["i"], obs_raw["i"])
    # Dynamics and masks are untouched — only the observation is impoverished.
    np.testing.assert_array_equal(wrapped.action_masks(), raw.action_masks())


# ── Retired (see report for the full accounting) ─────────────────────────────
#
# - test_layout_covers_obs_exactly: DELETED as a pure duplicate.
#   test_combat_obs_v4.py::test_layout_self_consistency already asserts that
#   combat_obs_segments_f/i() sum to layout.f_dim/i_dim and match what
#   reset()/step() actually return, for both card_obs modes — the exact v4
#   equivalent of what this test pinned for the old flat layout.
#
# - test_layout_landmarks: DELETED. Its three landmarks no longer exist in
#   the form it pinned: `sl["player.dexterity"] == slice(9, 10)` was a v3
#   flat-offset coincidence with no v4 equivalent worth freezing (the
#   segment's EXISTENCE and behavior are pinned by test_dexterity_is_
#   observable in test_full_env.py, addressed by name, not position);
#   `sl["enemy0.identity"]`/`sl["hand0.onehot"]` addressed float one-hot
#   segments that v4 does not have at all — identity is now a plain int in
#   `enemies.ids`/`hand.ids` (the int half), covered by test_combat_obs_v4.py
#   (test_enemy_potion_relic_decode, test_positional_alignment_survives_a_
#   dead_enemy_and_empty_slots); and the damage_matrix-matches-build-output
#   check is trivially true by construction (build_combat_obs writes into
#   `layout.f_slices["damage_matrix"]` itself) and is exercised far more
#   rigorously by test_combat_obs_v4.py::test_damage_matrix_cell_matches_
#   decoded_action_with_a_dead_enemy_in_slot_0.
