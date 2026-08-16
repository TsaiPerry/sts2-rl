"""Tests for sts2_rl/previews.py — pipeline-accurate displayed numbers.

The previews must reproduce exactly what DamageCmd/BlockCmd will compute
(mirroring AttackIntent.GetSingleDamage and the game's on-card previews), and
must be pure reads: previewing never mutates combat state.

Run with:  py -m pytest test/test_previews.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import (
    BlockCmd,
    CombatState,
    CreatureCmd,
    PowerCmd,
    make_card,
)
from sts2_rl.monsters import Encounter, FuzzyWurmCrawler, FUZZY_WURM_ENCOUNTER
from sts2_rl.powers import (
    CorruptionPower,
    DexterityPower,
    FrailPower,
    IntangiblePower,
    StrengthPower,
    VulnerablePower,
    WeakPower,
)
from sts2_rl.previews import (
    card_base_block,
    card_base_damage,
    preview_card_block,
    preview_card_damage,
    preview_card_energy_cost,
    preview_incoming_damage,
    preview_total_incoming,
)
from sts2_rl.valueprops import ValueProp

TWO_CRAWLERS = Encounter(
    id="two_crawlers_test", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]
)


def _combat(encounter=FUZZY_WURM_ENCOUNTER, seed=0):
    return CombatState(rng=random.Random(seed), encounter=encounter)


# ── Incoming (enemy intent) previews ─────────────────────────────────────────


def test_incoming_base_damage():
    c = _combat()
    e = c.enemies[0]  # FIRST_ACID_GOOP: 4 damage × 1 hit
    p = preview_incoming_damage(c, e)
    assert (p.per_hit, p.hits, p.total, p.post_block) == (4, 1, 4, 4)


def test_incoming_enemy_strength_and_weak():
    c = _combat()
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, e, StrengthPower, 3)
    assert preview_incoming_damage(c, e).per_hit == 7
    PowerCmd.apply(c.hooks, e, WeakPower, 1)
    assert preview_incoming_damage(c, e).per_hit == 5   # int(7 * 0.75)


def test_incoming_player_vulnerable():
    c = _combat()
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, c.player, VulnerablePower, 2, applier=e)
    assert preview_incoming_damage(c, e).per_hit == 6   # int(4 * 1.5)


def test_incoming_intangible_cap():
    c = _combat()
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, e, StrengthPower, 20)
    PowerCmd.apply(c.hooks, c.player, IntangiblePower, 1)
    p = preview_incoming_damage(c, e)
    assert (p.per_hit, p.post_block) == (1, 1)


def test_incoming_post_block():
    c = _combat()
    BlockCmd.apply(c.hooks, c.player, 2)
    p = preview_incoming_damage(c, c.enemies[0])
    assert (p.per_hit, p.post_block) == (4, 2)


def test_no_preview_for_non_attack_or_stunned():
    c = _combat()
    e = c.enemies[0]
    e._move_key = "INHALE"                      # BUFF move
    assert preview_incoming_damage(c, e) is None
    e._move_key = "ACID_GOOP"
    assert preview_incoming_damage(c, e) is not None
    CreatureCmd.stun(c.hooks, e)                # will skip the move
    assert preview_incoming_damage(c, e) is None


def test_total_incoming_absorbs_block_sequentially():
    c = _combat(TWO_CRAWLERS)
    BlockCmd.apply(c.hooks, c.player, 5)
    # Both crawlers attack for 4; block 5 absorbs 4 then 1 → 3 HP lost.
    assert preview_total_incoming(c) == 3
    hp = c.player.hp
    c.end_turn()
    assert hp - c.player.hp == 3


def test_preview_matches_reality_over_multiple_turns():
    """Property: with no cards played, HP lost during end_turn equals the
    preview — through the crawler's attack → strength buff → boosted attack
    cycle (the buffed turns exercise the additive-modifier path)."""
    c = _combat(seed=123)
    saw_buffed_attack = False
    for _ in range(6):
        if c.is_over:
            break
        expected = preview_total_incoming(c)
        if expected > 4:
            saw_buffed_attack = True
        hp_before = c.player.hp
        c.end_turn()
        assert hp_before - c.player.hp == expected
    assert saw_buffed_attack


# ── Card previews ─────────────────────────────────────────────────────────────


def test_card_damage_preview_pipeline():
    c = _combat()
    e = c.enemies[0]
    strike = make_card("strike")
    assert preview_card_damage(c, strike, e) == 6
    PowerCmd.apply(c.hooks, c.player, StrengthPower, 3)
    assert preview_card_damage(c, strike, e) == 9
    PowerCmd.apply(c.hooks, e, VulnerablePower, 2, applier=c.player)
    # Round-6 obs-parity fix: the game's own preview pipeline
    # (Hook.ModifyDamageInternal, decimal arithmetic — Hook.cs:2511-2539)
    # never truncates mid-pipeline; only its UI text call (DynamicVar.
    # ToHighlightedString) casts to int, a call site this preview module
    # doesn't reach. 9 * 1.5 stays 13.5, not int(9 * 1.5) == 13.
    assert preview_card_damage(c, strike, e) == 13.5
    PowerCmd.apply(c.hooks, c.player, WeakPower, 1)
    assert preview_card_damage(c, strike, e) == pytest.approx(10.125)  # 9 * 1.5 * 0.75


def test_card_damage_preview_dynamic_cards():
    c = _combat()
    e = c.enemies[0]
    body_slam = make_card("body_slam")
    assert preview_card_damage(c, body_slam, e) == 0
    BlockCmd.apply(c.hooks, c.player, 7)
    assert card_base_damage(c, body_slam, e) == 7
    assert preview_card_damage(c, body_slam, e) == 7
    # Cards with no enemy damage preview as None.
    assert preview_card_damage(c, make_card("defend"), e) is None


def test_card_block_preview_pipeline():
    c = _combat()
    defend = make_card("defend")
    assert preview_card_block(c, defend) == 5
    PowerCmd.apply(c.hooks, c.player, DexterityPower, 3)
    assert preview_card_block(c, defend) == 8
    PowerCmd.apply(c.hooks, c.player, FrailPower, 1)
    assert preview_card_block(c, defend) == 6           # int(8 * 0.75)
    assert preview_card_block(c, make_card("strike")) is None


def test_card_block_preview_props_none_skips_modifiers():
    """Obs-parity fix (89U diff vs live game dump, `hand.f` field offset
    21): the game's own DecisionDumper (SpireBot's
    `CombatObsWriter.cs:470`) reads this observation field via
    `Hook.ModifyBlock(..., default, card, null, ...)` — `default(ValueProp)`
    carries no `.Move` flag, so Dexterity's `ModifyBlockAdditive` and
    Frail's `ModifyBlockMultiplicative` (both gated on
    `props.IsPoweredCardOrMonsterMoveBlock()`, which requires `.Move`) are
    no-ops for that specific call. `preview_card_block(..., props=
    ValueProp.NONE)` must reproduce that — the raw base block, unaffected
    by any modifier — while the default (`ValueProp.MOVE`, used by every
    other caller: probes.py, the test above) keeps applying them."""
    c = _combat()
    defend = make_card("defend")
    PowerCmd.apply(c.hooks, c.player, DexterityPower, 3)
    PowerCmd.apply(c.hooks, c.player, FrailPower, 1)
    assert preview_card_block(c, defend, props=ValueProp.NONE) == 5


def test_hand_f_block_preview_field_unaffected_by_dexterity_or_frail():
    """`full_env.card_features`'s field 21 (`hand.f`'s block-preview slot)
    must equal field 20 (raw base block) whenever Dexterity/Frail are
    active — the game's DecisionDumper captures this field with no `.Move`
    prop, so those modifiers never apply to it (see `preview_card_block`'s
    docstring). Regression test for the 89U obs-parity diff (224 hand.f
    field-21 mismatches, all Defend/Impervious/True Grit-shaped: sim showed
    a Frail/Dexterity-adjusted value, the live game dump showed the raw
    base block)."""
    from sts2_rl.full_env import card_features

    c = _combat()
    defend = make_card("defend")
    PowerCmd.apply(c.hooks, c.player, DexterityPower, 3)
    PowerCmd.apply(c.hooks, c.player, FrailPower, 1)
    f = card_features(c, defend)
    assert f[20] == f[21]                                # both == base_block/ABS_SCALE
    assert f[20] == pytest.approx(5 / 100.0)


def test_card_base_block_prefers_calc_block():
    # calc_block is the block analog of calc_damage (card_base_damage,
    # previews.py:168-180): preferred over the static declaration.
    c = _combat()
    card = make_card("iron_wave")
    assert card_base_block(c, card) == card.base_block
    card.calc_block = lambda ctx, target=None: 42   # stub hook
    assert card_base_block(c, card) == 42


def test_preview_card_block_routes_through_base_helper():
    c = _combat()
    card = make_card("iron_wave")
    card.calc_block = lambda ctx, target=None: 42
    # 42 then flows through the MOVE pipeline (dex 0 here -> unchanged)
    assert preview_card_block(c, card) == 42


def test_card_energy_cost_preview():
    c = _combat()
    defend = make_card("defend")
    assert preview_card_energy_cost(c, defend) == 1
    PowerCmd.apply(c.hooks, c.player, CorruptionPower, 1)
    assert preview_card_energy_cost(c, defend) == 0     # Corruption: skills cost 0
    whirlwind = make_card("whirlwind")
    assert preview_card_energy_cost(c, whirlwind) == c.player.energy


# ── Declarative base stats (Card properties) ─────────────────────────────────


def test_declarative_base_stats_track_upgrades():
    strike = make_card("strike")
    assert (strike.base_damage, strike.base_hits) == (6, 1)
    strike.upgrade()
    assert strike.base_damage == 9

    twin = make_card("twin_strike")
    assert (twin.base_damage, twin.base_hits) == (5, 2)

    defend = make_card("defend")
    assert defend.base_block == 5
    assert defend.base_damage is None
    defend.upgrade()
    assert defend.base_block == 8

    bash = make_card("bash")
    assert bash.magic_number == 2       # Vulnerable stacks
    assert make_card("offering").base_hp_loss > 0


# ── Purity ────────────────────────────────────────────────────────────────────


def test_previews_are_pure_reads():
    c = _combat(seed=7)
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, c.player, VulnerablePower, 2, applier=e)
    PowerCmd.apply(c.hooks, e, StrengthPower, 2)

    snapshot = (
        c.player.hp, c.player.block, c.player.energy,
        e.hp, e.block,
        {pid: pw.amount for pid, pw in c.player.powers.items()},
        {pid: pw.amount for pid, pw in e.powers.items()},
        len(c.history.entries),
        c._rng.getstate(),
    )
    preview_incoming_damage(c, e)
    preview_total_incoming(c)
    for card in c.player.hand:
        preview_card_damage(c, card, e)
        preview_card_block(c, card)
        preview_card_energy_cost(c, card)
    after = (
        c.player.hp, c.player.block, c.player.energy,
        e.hp, e.block,
        {pid: pw.amount for pid, pw in c.player.powers.items()},
        {pid: pw.amount for pid, pw in e.powers.items()},
        len(c.history.entries),
        c._rng.getstate(),
    )
    assert snapshot == after
