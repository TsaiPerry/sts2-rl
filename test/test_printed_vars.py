"""Tests for the `card/_printed_vars` audit fix (Task 24): 23 cards declared
a printed C# var (HpLossVar/DamageVar/BlockVar/GoldVar/DynamicVar) with no
matching `_`-attribute in `_init_vars`, so `Card.base_damage` / `base_block`
/ `base_hp_loss` / `base_gold` / `magic_number` misreported them — which
`full_env.card_features` encodes into the observation vector.

Per card this checks: (1) the printed-number API now reports the C# value,
and (2) card BEHAVIOUR (the number actually dealt/applied/gained) is
unchanged — same numbers, only the previously-missing read API fixed.

Run with:  py -m pytest test/test_printed_vars.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, PowerCmd
from sts2_rl.cards import (
    BadLuckCard,
    BeckonCard,
    BreakthroughCard,
    BurnCard,
    CardType,
    ColossusCard,
    CorruptionCard,
    DebtCard,
    DecayCard,
    DoubtCard,
    EquilibriumCard,
    ExpectAFightCard,
    FeelNoPainCard,
    GuiltyCard,
    InfectionCard,
    NormalityCard,
    PactsEndCard,
    RollingBoulderCard,
    ShameCard,
    SlimedCard,
    SpoilsMapCard,
    StampedeCard,
    StrikeCard,
    ToxicCard,
    WitherCard,
    make_card,
)
from sts2_rl.cmds import CardPileCmd
from sts2_rl.run import RunState


# ── Helpers (mirror test_curses.py / test_colorless.py) ────────────────────

def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


def combat(deck, seed: int = 0) -> CombatState:
    """Combat whose starting deck is exactly `deck` (<=5 cards => all in hand)."""
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def give(cs: CombatState, card):
    """Add a card to the hand through the pile command (registers it as a
    hook listener and sets `card.combat` -- required by the live
    `magic_number` overrides on Normality/Guilty/ExpectAFight)."""
    CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
    return card


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


def turn_end_in_hand(cs: CombatState) -> None:
    cs.hooks.on_player_turn_end(cs.player)
    cs._process_turn_end_cards()


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# HpLossVar cards: bad_luck, beckon, breakthrough
# ══════════════════════════════════════════════════════════════════════════

class TestHpLossVar:
    def test_bad_luck_base_hp_loss(self):
        assert BadLuckCard().base_hp_loss == 13

    def test_bad_luck_behavior_unchanged(self):
        """Behaviour pin: still loses exactly 13, unblockable."""
        cs = fresh()
        give(cs, BadLuckCard())
        cs.player.block = 50
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 13

    def test_beckon_base_hp_loss(self):
        assert BeckonCard().base_hp_loss == 6

    def test_beckon_behavior_unchanged(self):
        cs = fresh()
        give(cs, BeckonCard())
        cs.player.block = 50
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 6

    def test_breakthrough_base_hp_loss_and_damage(self):
        card = BreakthroughCard()
        assert card.base_hp_loss == 1
        assert card.base_damage == 9  # unaffected pre-existing var

    def test_breakthrough_behavior_unchanged(self):
        cs = fresh()
        before_hp = cs.player.hp
        before_enemy = cs.enemy.hp
        play(cs, BreakthroughCard())
        assert cs.player.hp == before_hp - 1
        assert cs.enemy.hp == before_enemy - 9


# ══════════════════════════════════════════════════════════════════════════
# DamageVar (Unpowered|Move) status/curse cards: burn, decay, infection, toxic
# ══════════════════════════════════════════════════════════════════════════

class TestUnpoweredDamageVar:
    def test_burn_base_damage(self):
        assert BurnCard().base_damage == 2

    def test_burn_behavior_unchanged(self):
        cs = fresh()
        give(cs, BurnCard())
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 2

    def test_decay_base_damage(self):
        assert DecayCard().base_damage == 2

    def test_decay_behavior_unchanged_and_blockable(self):
        cs = fresh()
        give(cs, DecayCard())
        cs.player.block = 2
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before  # blocked, matches pre-fix test_curses.py

    def test_infection_base_damage(self):
        assert InfectionCard().base_damage == 3

    def test_infection_behavior_unchanged(self):
        cs = fresh()
        give(cs, InfectionCard())
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 3

    def test_toxic_base_damage(self):
        assert ToxicCard().base_damage == 5

    def test_toxic_behavior_unchanged(self):
        cs = fresh()
        give(cs, ToxicCard())
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 5

    def test_wither_base_damage_mirrors_live_damage_property(self):
        """Wither's damage grows via FakeUpgrade, not `_on_upgrade`, so
        `base_damage` is overridden to report the live `damage` property
        instead of a static `_damage` attribute."""
        card = WitherCard()
        assert card.base_damage == 3 == card.damage
        card.fake_upgrade()
        assert card.base_damage == 6 == card.damage
        card.fake_upgrade()
        assert card.base_damage == 9 == card.damage

    def test_wither_behavior_unchanged(self):
        cs = fresh()
        card = WitherCard()
        card.fake_upgrade()  # 6 damage
        give(cs, card)
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 6


# ══════════════════════════════════════════════════════════════════════════
# PowerVar<WeakPower> / generic "Frail" DynamicVar: doubt, shame
# ══════════════════════════════════════════════════════════════════════════

class TestDebuffVar:
    def test_doubt_magic_number(self):
        assert DoubtCard().magic_number == 1

    def test_doubt_behavior_unchanged(self):
        cs = fresh()
        give(cs, DoubtCard())
        turn_end_in_hand(cs)
        assert cs.player.powers["weak"].amount == 1

    def test_shame_magic_number(self):
        assert ShameCard().magic_number == 1

    def test_shame_behavior_unchanged(self):
        cs = fresh()
        give(cs, ShameCard())
        turn_end_in_hand(cs)
        assert cs.player.powers["frail"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# Generic "Power" DynamicVar fed straight into PowerCmd.Apply: colossus,
# corruption, equilibrium, stampede (same shape as Rage/Panache's existing
# `_power_amount` convention)
# ══════════════════════════════════════════════════════════════════════════

class TestPowerAmountVar:
    def test_colossus_block_and_magic_number(self):
        card = ColossusCard()
        assert card.base_block == 5          # unaffected pre-existing var
        assert card.magic_number == 1         # was None

    def test_colossus_behavior_unchanged(self):
        cs = fresh()
        play(cs, ColossusCard())
        assert cs.player.block == 5
        assert cs.player.powers["colossus"].amount == 1

    def test_corruption_magic_number(self):
        assert CorruptionCard().magic_number == 1

    def test_corruption_behavior_unchanged(self):
        cs = fresh()
        play(cs, CorruptionCard())
        assert cs.player.powers["corruption"].amount == 1

    def test_equilibrium_block_and_magic_number(self):
        card = EquilibriumCard()
        assert card.base_block == 13
        assert card.magic_number == 1

    def test_equilibrium_behavior_unchanged(self):
        cs = fresh()
        play(cs, EquilibriumCard())
        assert cs.player.block == 13
        assert cs.player.powers["retain_hand"].amount == 1

    def test_stampede_magic_number(self):
        assert StampedeCard().magic_number == 1

    def test_stampede_behavior_unchanged(self):
        cs = fresh()
        play(cs, StampedeCard())
        assert cs.player.powers["stampede"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# Feel No Pain: the wrong-attribute variant (was `_block`, now
# `_power_amount`) -- behaviour pin explicitly requested by the brief.
# ══════════════════════════════════════════════════════════════════════════

class TestFeelNoPain:
    def test_base_block_is_now_none(self):
        """The card itself grants no block -- that belongs to FeelNoPainPower.
        Before the fix `base_block` wrongly returned 3."""
        assert FeelNoPainCard().base_block is None

    def test_magic_number_is_now_three(self):
        assert FeelNoPainCard().magic_number == 3

    def test_gains_block_still_false(self):
        # Unaffected by the rename -- GainsBlock is declared separately.
        assert not FeelNoPainCard().gains_block

    def test_behavior_unchanged(self):
        """Behaviour pin: playing it still grants FeelNoPainPower(3), and the
        player gains no block from the card itself."""
        cs = fresh()
        play(cs, FeelNoPainCard())
        assert cs.player.powers["feel_no_pain"].amount == 3
        assert cs.player.block == 0

    def test_upgrade_behavior_unchanged(self):
        cs = fresh()
        card = FeelNoPainCard()
        card.upgrade()
        play(cs, card)
        assert cs.player.powers["feel_no_pain"].amount == 4


# ══════════════════════════════════════════════════════════════════════════
# CardsVar: pacts_end (renamed _required_exhausted -> _cards), slimed
# ══════════════════════════════════════════════════════════════════════════

class TestCardsVar:
    def test_pacts_end_magic_number(self):
        assert PactsEndCard().magic_number == 3

    def test_pacts_end_behavior_unchanged(self):
        cs = fresh()
        cs.player.exhaust_pile = [StrikeCard(), StrikeCard()]  # only 2
        before = cs.enemy.hp
        play(cs, PactsEndCard())
        assert cs.enemy.hp == before  # < 3 exhausted -> no damage

        cs = fresh()
        cs.player.exhaust_pile = [StrikeCard(), StrikeCard(), StrikeCard()]
        before = cs.enemy.hp
        play(cs, PactsEndCard())
        assert cs.enemy.hp == before - 17

    def test_slimed_magic_number(self):
        assert SlimedCard().magic_number == 1

    def test_slimed_behavior_unchanged(self):
        cs = fresh()
        card = SlimedCard()
        cs.player.hand.append(card)
        cs.player.energy = 10
        hand_size_before = len(cs.player.hand)
        assert cs.play_card(len(cs.player.hand) - 1)
        assert card in cs.player.exhaust_pile
        assert card not in cs.player.hand
        # Played out (-1) then drew exactly 1 card back in.
        assert len(cs.player.hand) == hand_size_before - 1 + 1


# ══════════════════════════════════════════════════════════════════════════
# GoldVar: debt, spoils_map -- behaviour pin explicitly requested by the
# brief. No `_MAGIC_ATTRS` slot exists for gold (matches the existing
# unexposed `_gold` on Hand of Greed); the fix adds a sibling `base_gold`
# property instead (cards/base.py), mirroring `base_hp_loss`'s shape.
# ══════════════════════════════════════════════════════════════════════════

class TestGoldVar:
    def test_debt_base_gold(self):
        assert DebtCard().base_gold == 10

    def test_debt_behavior_unchanged(self):
        """Behaviour pin: still drains min(10, balance) gold, and still has
        no HP effect (matches test_curses.py's existing pin)."""
        cs = fresh(player_gold=10)
        give(cs, DebtCard())
        before_hp = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before_hp
        assert cs.gold_spent == 10

    def test_debt_behavior_caps_at_balance(self):
        cs = fresh(player_gold=4)
        give(cs, DebtCard())
        turn_end_in_hand(cs)
        assert cs.gold_spent == 4

    def test_spoils_map_base_gold(self):
        assert SpoilsMapCard().base_gold == 600

    def test_spoils_map_behavior_unchanged(self):
        run = fresh_run()
        card = run.add_card(make_card("spoils_map"))
        before = run.gold
        paid = card.on_quest_complete(run)
        assert paid == 600
        assert run.gold == before + 600
        assert card not in run.deck


# ══════════════════════════════════════════════════════════════════════════
# Live (non-constant) magic numbers: guilty, normality, expect_a_fight.
# None of C#'s CanonicalVars for these three is a fixed number -- each is
# recomputed at read time (a live countdown or a live hand-dependent count),
# so `magic_number` is overridden as a property instead of stored in
# `_init_vars`, matching the shape of the existing `calc_damage` override
# point used for combat-state-dependent damage.
# ══════════════════════════════════════════════════════════════════════════

class TestLiveMagicNumbers:
    def test_guilty_counts_down(self):
        run = fresh_run()
        card = run.add_card(make_card("guilty"))
        assert card.magic_number == 5
        for expected in (4, 3, 2, 1, 0):
            card.after_combat_end(run)
            assert card.magic_number == expected

    def test_normality_counts_down_as_cards_are_played(self):
        # No combat registered yet -- falls back to the static start value.
        assert NormalityCard().magic_number == 3

        cs = fresh()  # 9-card starter deck, opening hand of 5
        card = give(cs, NormalityCard())
        cs.player.energy = 10
        assert card.magic_number == 3
        for expected in (2, 1, 0):
            playable = next(
                i for i, c in enumerate(cs.player.hand) if c.is_playable
            )
            assert cs.play_card(playable)
            assert card.magic_number == expected

    def test_expect_a_fight_counts_attacks_in_hand(self):
        # No combat registered yet -- falls back to 0.
        assert ExpectAFightCard().magic_number == 0

        deck = [StrikeCard(), StrikeCard(), make_card("defend"),
                ExpectAFightCard(), make_card("defend")]
        cs = combat(deck)
        card = next(c for c in cs.player.hand if isinstance(c, ExpectAFightCard))
        attacks_in_hand = sum(
            1 for c in cs.player.hand if c.card_type == CardType.ATTACK
        )
        assert card.magic_number == attacks_in_hand

    def test_expect_a_fight_behavior(self):
        deck = [StrikeCard(), StrikeCard(), make_card("defend"),
                ExpectAFightCard(), make_card("defend")]
        cs = combat(deck)
        card = next(c for c in cs.player.hand if isinstance(c, ExpectAFightCard))
        attacks = sum(1 for c in cs.player.hand if c.card_type == CardType.ATTACK)
        cs.player.energy = 5
        idx = cs.player.hand.index(card)
        before_energy = cs.player.energy
        assert cs.play_card(idx)
        # Cost 2, then gains `attacks` energy back.
        assert cs.player.energy == before_energy - 2 + attacks
        assert "no_energy_gain" in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# Rolling Boulder's second var (IncrementAmount): documented, not surfaced
# by magic_number (the primary `_power_amount` slot wins the scan) -- the
# growth itself lives in RollingBoulderPower.INCREMENT (powers.py), which
# this test confirms still agrees with the card's printed number.
# ══════════════════════════════════════════════════════════════════════════

class TestRollingBoulderSecondVar:
    def test_increment_attribute_present(self):
        card = RollingBoulderCard()
        assert card._increase == 5           # DynamicVar("IncrementAmount", 5m)
        assert card.magic_number == 5         # _power_amount still wins the scan

    def test_increment_matches_power_growth(self):
        from sts2_rl.powers import RollingBoulderPower
        assert RollingBoulderCard()._increase == RollingBoulderPower.INCREMENT
