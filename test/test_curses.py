"""
Tests for the curse card pool (all 18 curses from the game source) and the
engine keywords they introduced: Retain (Poor Sleep) and the auto_play
distinction on should_play_card (Enthralled vs Normality).

Run with:  py -m pytest test/test_curses.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import (
    AscendersBaneCard,
    BadLuckCard,
    CardRarity,
    CardType,
    ClumsyCard,
    CurseOfTheBellCard,
    DebtCard,
    DecayCard,
    DoubtCard,
    EnthralledCard,
    FollyCard,
    GreedCard,
    GuiltyCard,
    InjuryCard,
    NormalityCard,
    PoorSleepCard,
    RegretCard,
    ShameCard,
    SporeMindCard,
    StrikeCard,
    WritheCard,
    make_card,
)
from sts2_rl.cards import CURSE_POOL, curse_pool_ids, random_curses
from sts2_rl.cmds import CardPileCmd


ALL_CURSES = (
    AscendersBaneCard,
    BadLuckCard,
    ClumsyCard,
    CurseOfTheBellCard,
    DebtCard,
    DecayCard,
    DoubtCard,
    EnthralledCard,
    FollyCard,
    GreedCard,
    GuiltyCard,
    InjuryCard,
    NormalityCard,
    PoorSleepCard,
    RegretCard,
    ShameCard,
    SporeMindCard,
    WritheCard,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck)."""
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    """Combat whose starting deck is exactly `deck` (≤5 cards ⇒ all in hand)."""
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def give(cs: CombatState, card):
    """Add a card to the hand through the pile command (registers hooks)."""
    CardPileCmd.add_to_hand(cs.hooks, cs.player, card)
    return card


def turn_end_in_hand(cs: CombatState) -> None:
    """The player-side turn-end slice of end_turn (hooks, then in-hand
    effects) without running the enemy turn."""
    cs.hooks.on_player_turn_end(cs.player)
    cs._process_turn_end_cards()


# ══════════════════════════════════════════════════════════════════════════
# Shared curse properties
# ══════════════════════════════════════════════════════════════════════════

class TestCursePool:
    def test_all_registered_with_distinct_ids(self):
        ids = {cls.id for cls in ALL_CURSES}
        assert len(ids) == 18
        for cls in ALL_CURSES:
            assert type(make_card(cls.id)) is cls

    def test_type_and_rarity(self):
        for cls in ALL_CURSES:
            assert cls.card_type == CardType.CURSE
            assert cls.rarity == CardRarity.CURSE

    def test_never_upgradable(self):
        for cls in ALL_CURSES:
            assert cls.max_upgrade_level == 0
            assert not cls().is_upgradable

    def test_playability(self):
        # Only Enthralled and Spore Mind lack the Unplayable keyword.
        playable = {cls for cls in ALL_CURSES if cls.is_playable}
        assert playable == {EnthralledCard, SporeMindCard}

    def test_keyword_flags_match_source(self):
        assert AscendersBaneCard.eternal and AscendersBaneCard.is_ethereal
        assert BadLuckCard.eternal
        assert ClumsyCard.is_ethereal and not ClumsyCard.eternal
        assert CurseOfTheBellCard.eternal
        assert EnthralledCard.eternal
        assert FollyCard.eternal and FollyCard.innate and FollyCard.is_ethereal
        assert GreedCard.eternal
        assert PoorSleepCard.retain
        assert SporeMindCard.exhausts
        assert WritheCard.innate and not WritheCard.is_ethereal

    def test_curse_pool_matches_source(self):
        # CurseCardPool.cs lists all 18 curses.
        assert set(CURSE_POOL) == {cls.id for cls in ALL_CURSES}
        assert len(CURSE_POOL) == 18

    def test_generatable_subset_matches_source(self):
        # The 8 curses with CanBeGeneratedByModifiers = false are excluded
        # from random curse generation.
        excluded = {
            AscendersBaneCard.id, BadLuckCard.id, CurseOfTheBellCard.id,
            EnthralledCard.id, FollyCard.id, GreedCard.id,
            PoorSleepCard.id, SporeMindCard.id,
        }
        assert set(curse_pool_ids()) == set(CURSE_POOL) - excluded
        assert set(curse_pool_ids(generatable_only=False)) == set(CURSE_POOL)

    def test_random_curses_draws_only_generatable(self):
        rng = random.Random(0)
        generatable = set(curse_pool_ids())
        drawn = random_curses(rng, 200)
        assert len(drawn) == 200
        assert {c.id for c in drawn} == generatable  # 200 draws hit all 10

    def test_random_curses_distinct(self):
        rng = random.Random(0)
        # Sere Talon / Neow's Bones pick distinct curses.
        drawn = random_curses(rng, 2, distinct=True)
        assert len(drawn) == 2
        assert drawn[0].id != drawn[1].id
        # Asking for more than the pool holds caps at the pool size.
        drawn = random_curses(rng, 99, distinct=True)
        assert sorted(c.id for c in drawn) == sorted(curse_pool_ids())

    def test_unplayable_curses_cannot_be_played(self):
        cs = fresh()
        card = give(cs, InjuryCard())
        cs.player.energy = 10
        assert not cs.play_card(cs.player.hand.index(card))
        assert card in cs.player.hand


# ══════════════════════════════════════════════════════════════════════════
# Ethereal / innate / retain movement
# ══════════════════════════════════════════════════════════════════════════

class TestPileMovement:
    def test_ethereal_curses_exhaust_at_turn_end(self):
        for cls in (AscendersBaneCard, ClumsyCard, FollyCard):
            cs = fresh()
            card = give(cs, cls())
            turn_end_in_hand(cs)
            assert card in cs.player.exhaust_pile, cls.id

    def test_dead_curses_are_discarded_with_the_hand(self):
        for cls in (CurseOfTheBellCard, DebtCard, GreedCard, GuiltyCard, InjuryCard):
            cs = fresh()
            card = give(cs, cls())
            turn_end_in_hand(cs)
            cs.player.discard_hand()
            assert card in cs.player.discard_pile, cls.id

    def test_writhe_is_innate(self):
        deck = [StrikeCard() for _ in range(7)] + [WritheCard()]
        cs = combat(deck)
        assert any(isinstance(c, WritheCard) for c in cs.player.hand)

    def test_poor_sleep_is_retained_across_turns(self):
        cs = fresh()
        card = give(cs, PoorSleepCard())
        cs.end_turn()
        assert card in cs.player.hand
        cs.end_turn()
        assert card in cs.player.hand

    def test_non_retain_cards_still_flushed(self):
        cs = fresh()
        card = give(cs, PoorSleepCard())
        flushed = [c for c in cs.player.hand if not c.retain]
        cs.player.discard_hand()
        assert cs.player.hand == [card]
        assert all(c in cs.player.discard_pile for c in flushed)


# ══════════════════════════════════════════════════════════════════════════
# Turn-end-in-hand effects
# ══════════════════════════════════════════════════════════════════════════

class TestTurnEndEffects:
    def test_bad_luck_loses_13_unblockable(self):
        cs = fresh()
        card = give(cs, BadLuckCard())
        cs.player.block = 50
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 13
        assert card in cs.player.discard_pile

    def test_decay_deals_2_blockable(self):
        cs = fresh()
        give(cs, DecayCard())
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 2

        cs = fresh()
        give(cs, DecayCard())
        cs.player.block = 2
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before

    def test_doubt_applies_1_weak_with_skipped_first_tick(self):
        cs = fresh()
        give(cs, DoubtCard())
        turn_end_in_hand(cs)
        weak = cs.player.powers["weak"]
        assert weak.amount == 1
        # PowerCmd.apply marks player debuffs to skip their first tick, so the
        # Weak survives the enemy side-end that follows this turn end.
        assert weak.skip_next_tick

    def test_shame_applies_1_frail(self):
        cs = fresh()
        give(cs, ShameCard())
        turn_end_in_hand(cs)
        frail = cs.player.powers["frail"]
        assert frail.amount == 1
        assert frail.skip_next_tick

    def test_regret_loses_hp_equal_to_hand_size_unblockable(self):
        cs = fresh()  # opening hand of 5
        give(cs, RegretCard())  # hand of 6, Regret counts itself
        cs.player.block = 50
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before - 6

    def test_regret_does_nothing_from_other_piles(self):
        cs = fresh()
        card = RegretCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        before = cs.player.hp
        cs.end_turn()
        assert cs.player.hp <= before  # only enemy damage, no Regret snapshot
        assert card._cards_in_hand == 0

    def test_debt_has_no_hp_effect(self):
        # Debt's gold loss is not simulated (the sim has no gold).
        cs = fresh()
        give(cs, DebtCard())
        before = cs.player.hp
        turn_end_in_hand(cs)
        assert cs.player.hp == before


# ══════════════════════════════════════════════════════════════════════════
# Playable curses
# ══════════════════════════════════════════════════════════════════════════

class TestSporeMind:
    def test_play_costs_1_and_exhausts(self):
        cs = fresh()
        card = give(cs, SporeMindCard())
        cs.player.energy = 3
        assert cs.play_card(cs.player.hand.index(card))
        assert cs.player.energy == 2
        assert card in cs.player.exhaust_pile


class TestEnthralled:
    def test_blocks_other_manual_plays_while_in_hand(self):
        cs = fresh()
        give(cs, EnthralledCard())
        cs.player.energy = 10
        strike_idx = next(
            i for i, c in enumerate(cs.player.hand) if isinstance(c, StrikeCard)
        )
        assert not cs.play_card(strike_idx)
        # valid_actions only offers end-turn and Enthralled itself.
        offered = [a - 1 for a in cs.valid_actions() if a != 0]
        assert all(isinstance(cs.player.hand[i], EnthralledCard) for i in offered)

    def test_playing_it_costs_2_and_unblocks(self):
        cs = fresh()
        card = give(cs, EnthralledCard())
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(card))
        assert cs.player.energy == 8
        assert card in cs.player.discard_pile  # no Exhaust keyword
        strike_idx = next(
            i for i, c in enumerate(cs.player.hand) if isinstance(c, StrikeCard)
        )
        assert cs.play_card(strike_idx)

    def test_allows_auto_plays(self):
        cs = fresh()
        give(cs, EnthralledCard())
        strike = next(c for c in cs.player.hand if isinstance(c, StrikeCard))
        assert not cs.hooks.should_play_card(strike)
        assert cs.hooks.should_play_card(strike, auto_play=True)

    def test_no_restriction_from_other_piles(self):
        cs = fresh()
        card = EnthralledCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        cs.player.energy = 10
        strike_idx = next(
            i for i, c in enumerate(cs.player.hand) if isinstance(c, StrikeCard)
        )
        assert cs.play_card(strike_idx)


class TestNormality:
    def test_limits_to_3_card_plays_per_turn(self):
        cs = fresh()
        give(cs, NormalityCard())
        cs.player.energy = 10
        for _ in range(3):
            playable = next(
                i for i, c in enumerate(cs.player.hand) if c.is_playable
            )
            assert cs.play_card(playable)
        playable = next(i for i, c in enumerate(cs.player.hand) if c.is_playable)
        assert not cs.play_card(playable)
        assert cs.valid_actions() == [0]

    def test_blocks_auto_plays_too(self):
        # Normality's ShouldPlay ignores the AutoPlayType argument.
        cs = fresh()
        give(cs, NormalityCard())
        cs.player.energy = 10
        for _ in range(3):
            playable = next(
                i for i, c in enumerate(cs.player.hand) if c.is_playable
            )
            assert cs.play_card(playable)
        strike = next(c for c in cs.player.hand if isinstance(c, StrikeCard))
        assert not cs.hooks.should_play_card(strike, auto_play=True)

    def test_resets_next_turn(self):
        cs = fresh()
        give(cs, NormalityCard())
        cs.player.energy = 10
        for _ in range(3):
            playable = next(
                i for i, c in enumerate(cs.player.hand) if c.is_playable
            )
            assert cs.play_card(playable)
        cs.end_turn()
        assert not cs.is_over
        cs.player.energy = 10
        give(cs, NormalityCard())  # ensure one is in hand this turn too
        playable = next(i for i, c in enumerate(cs.player.hand) if c.is_playable)
        assert cs.play_card(playable)

    def test_no_restriction_from_other_piles(self):
        cs = fresh()
        card = NormalityCard()
        CardPileCmd.add_to_discard(cs.hooks, cs.player, card)
        cs.player.energy = 10
        for _ in range(4):
            playable = next(
                (i for i, c in enumerate(cs.player.hand) if c.is_playable), None
            )
            if playable is None or cs.is_over:
                break
            assert cs.play_card(playable)
