"""Tests for the card-GENERATION pool family (Task 30, audit gap queue
mechanisms `potion/_filter_for_combat_event_rarity` and the playable-Status /
`CanBeGeneratedInCombat` cluster).

Mechanism A: CardFactory.FilterForCombat (CardFactory.cs:159-162) is

    cards.Where(c => c.CanBeGeneratedInCombat
                   && c.Rarity != CardRarity.Basic
                   && c.Rarity != CardRarity.Ancient
                   && c.Rarity != CardRarity.Event).Distinct()

-- it drops THREE rarities (Basic, Ancient, Event), not two. cards/pool.py's
`pool_card_ids` (the FilterForCombat port) only excluded Basic/Ancient plus
the CanBeGeneratedInCombat flag; the Event clause was missing.

Mechanism B: two mismatched-flag/keyword shapes on a small card cluster --

1. Disintegration.cs:16 / MindRot.cs:14 / Sloth.cs:16 / WasteAway.cs:15 and
   FranticEscape.cs:30 all override `CanBeGeneratedInCombat => false` with NO
   `CanBeGeneratedByModifiers` override (CardModel.cs:648 default `=> true`).
   The sim's `_ChoosableCurse` base (knowledge_curses.py) and frantic_escape.py
   had the flags backwards: `can_be_generated_in_combat` left at its True
   default and `can_be_generated_by_modifiers` turned off instead -- a flag
   neither C# card touches.
2. Disintegration.cs / MindRot.cs / Sloth.cs / WasteAway.cs declare no
   `CanonicalKeywords` override at all, so CardModel.cs:498's empty-array
   default applies and `CardKeyword.Unplayable` is never added to the card --
   these are PLAYABLE no-effect Statuses in the game, the same shape as
   Beckon (cards/beckon.py, which the sim already models as playable). The
   sim's `_ChoosableCurse` base set `is_playable = False`, which no C# card in
   the family does.

Run with:  py -m pytest test/test_card_generation_pool.py -v
"""
from __future__ import annotations

import pytest

from sts2_rl.cards import make_card, pool_card_ids, transform_options_in_combat
from sts2_rl.cards.base import CardRarity, _CARD_CLASSES
from sts2_rl.cards.pool import COLORLESS_POOL, IRONCLAD_POOL


# ═══════════════════════════════════════════════════════════════════════════
# Mechanism A -- pool_card_ids / FilterForCombat's missing Event clause
# ═══════════════════════════════════════════════════════════════════════════


class TestFilterForCombatDropsThreeRarities:
    """CardFactory.FilterForCombat (CardFactory.cs:159-162) excludes
    CanBeGeneratedInCombat=False cards and Basic/Ancient/Event rarities."""

    def test_event_rarity_card_excluded_from_pool_card_ids(self):
        # `clash` is a real ported Event-rarity card
        # (can_be_generated_in_combat=True today), so only the missing Event
        # clause could let it survive pool_card_ids's filter.
        assert _CARD_CLASSES["clash"].rarity == CardRarity.EVENT
        assert _CARD_CLASSES["clash"].can_be_generated_in_combat is True
        # "bash" is Basic (also dropped); "bludgeon" is Common, so it must
        # survive -- the probe isolates the Event clause specifically.
        probe_pool = ("bash", "clash", "bludgeon")
        ids = pool_card_ids(pool=probe_pool)
        assert "clash" not in ids
        assert ids == ["bludgeon"]

    def test_every_registered_event_card_would_leak_without_the_clause(self):
        # Documents the full blast radius of the missing clause: every
        # Event-rarity card ported so far has can_be_generated_in_combat=True,
        # so each one is a potential probe for this bug.
        event_ids = [cid for cid, c in _CARD_CLASSES.items()
                     if c.rarity == CardRarity.EVENT]
        assert event_ids  # sanity: the sim does have ported Event cards
        for cid in event_ids:
            probe_pool = ("strike", cid)
            assert cid not in pool_card_ids(pool=probe_pool), cid

    # ── Dormancy re-executed: neither real pool carries an Event card today ──

    def test_ironclad_pool_has_no_event_rarity_card(self):
        assert not any(
            _CARD_CLASSES[cid].rarity == CardRarity.EVENT for cid in IRONCLAD_POOL
        )

    def test_colorless_pool_has_no_event_rarity_card(self):
        assert not any(
            _CARD_CLASSES[cid].rarity == CardRarity.EVENT for cid in COLORLESS_POOL
        )

    def test_ironclad_pool_filtered_length_unaffected_by_the_fix(self):
        # Dormancy-preserving: 85 pool ids -> 78 after BASIC/ANCIENT (now also
        # EVENT, which contributes zero) are dropped.
        assert len(IRONCLAD_POOL) == 85
        assert len(pool_card_ids(pool=IRONCLAD_POOL)) == 78

    def test_colorless_pool_filtered_length_unaffected_by_the_fix(self):
        assert len(COLORLESS_POOL) == 53
        assert len(pool_card_ids(pool=COLORLESS_POOL)) == 50


# ═══════════════════════════════════════════════════════════════════════════
# Mechanism B -- the playable-Status / CanBeGeneratedInCombat cluster
# ═══════════════════════════════════════════════════════════════════════════


_CHOOSABLE_CURSE_IDS = ("disintegration", "mind_rot", "sloth", "waste_away")


class TestChoosableCurseFlags:
    """Disintegration.cs:16 / MindRot.cs:14 / Sloth.cs:16 / WasteAway.cs:15
    all override CanBeGeneratedInCombat => false with no
    CanBeGeneratedByModifiers override, and declare no CanonicalKeywords (so
    they are playable in the game)."""

    @pytest.mark.parametrize("card_id", _CHOOSABLE_CURSE_IDS)
    def test_playable_like_beckon(self, card_id):
        # No CanonicalKeywords override -> no Unplayable keyword -> playable,
        # the same shape as card/beckon (cards/beckon.py has no
        # is_playable override either).
        assert _CARD_CLASSES[card_id].is_playable is True
        assert _CARD_CLASSES["beckon"].is_playable is True

    @pytest.mark.parametrize("card_id", _CHOOSABLE_CURSE_IDS)
    def test_cannot_be_generated_in_combat(self, card_id):
        assert _CARD_CLASSES[card_id].can_be_generated_in_combat is False

    @pytest.mark.parametrize("card_id", _CHOOSABLE_CURSE_IDS)
    def test_can_be_generated_by_modifiers_stays_true(self, card_id):
        # CardModel.cs:648 default `=> true`; none of the four cards
        # overrides it.
        assert _CARD_CLASSES[card_id].can_be_generated_by_modifiers is True

    def test_on_play_still_a_no_op(self):
        # The playability fix must not give these cards an effect; C#'s
        # OnChosen (not OnPlay) is what applies the power, and only when
        # picked off the Curse of Knowledge screen.
        for card_id in _CHOOSABLE_CURSE_IDS:
            card = make_card(card_id)
            # on_play must not raise and must not require ctx internals.
            card.on_play(ctx=None)  # type: ignore[arg-type]


class TestFranticEscapeFlags:
    """FranticEscape.cs:30 overrides CanBeGeneratedInCombat => false with no
    CanBeGeneratedByModifiers override -- the same mismatch shape as the
    ChoosableCurse family, on a different base class."""

    def test_cannot_be_generated_in_combat(self):
        assert _CARD_CLASSES["frantic_escape"].can_be_generated_in_combat is False

    def test_can_be_generated_by_modifiers_stays_true(self):
        assert _CARD_CLASSES["frantic_escape"].can_be_generated_by_modifiers is True


class TestNeowsFuryFlag:
    """NeowsFury.cs:15 overrides CanBeGeneratedInCombat => false. The sim's
    Ancient rarity already keeps it out of pool_card_ids's rarity clause, so
    the OUTCOME matched even before this fix -- but CardModel.CanBeGeneratedInCombat
    (CardModel.cs:642) is the flag FilterForCombat actually reads, independent
    of rarity, so the card should set it explicitly like feed / hand_of_greed /
    hidden_gem do, rather than rely on the incidental rarity filter."""

    def test_cannot_be_generated_in_combat_explicit(self):
        assert _CARD_CLASSES["neows_fury"].can_be_generated_in_combat is False

    def test_still_excluded_from_ironclad_pool_ids_by_rarity_alone(self):
        # neows_fury is not even IN IRONCLAD_POOL (Ancient rarity cards are
        # listed for completeness in some pools but Neow's Fury is granted
        # only by Neow's Torment, never pool-generated) -- confirms the
        # dormancy claim independent of the flag fix.
        assert "neows_fury" not in IRONCLAD_POOL


# ═══════════════════════════════════════════════════════════════════════════
# A x B interaction check: does mechanism A's Event clause move mechanism B's
# dormancy through pool_card_ids?
# ═══════════════════════════════════════════════════════════════════════════


class TestMechanismInteraction:
    """The four ChoosableCurse cards and frantic_escape are CardRarity.STATUS,
    never CardRarity.EVENT, so mechanism A's new Event clause in
    pool_card_ids cannot change whether they pass or fail that filter --
    they were already excluded (now via can_be_generated_in_combat, before
    the B fix they leaked through it) and remain excluded after both fixes."""

    @pytest.mark.parametrize(
        "card_id", (*_CHOOSABLE_CURSE_IDS, "frantic_escape", "neows_fury")
    )
    def test_status_and_ancient_cards_unaffected_by_the_event_clause(self, card_id):
        assert _CARD_CLASSES[card_id].rarity != CardRarity.EVENT


# ═══════════════════════════════════════════════════════════════════════════
# Extra witness beyond the queue's recorded dormancy check: transform_options_
# in_combat's STATUS branch is a SECOND consumer of can_be_generated_in_combat
# that the queue's dormancy note (pool_card_ids / curse_pool_ids only) did not
# examine. It enumerates every registered Status card system-wide, not just
# IRONCLAD_POOL/COLORLESS_POOL, and is reachable today via the ported
# EntropyPower (cards/colorless_powers.py) transforming a Status card already
# reachable in a player's hand (Wound/Burn/Dazed/Slimed/Toxic/frantic_escape).
# ═══════════════════════════════════════════════════════════════════════════


class TestTransformOptionsStatusBranchExcludesTheFour:
    @pytest.mark.parametrize(
        "status_id",
        ("wound", "burn", "dazed", "slimed", "toxic", "beckon", "frantic_escape"),
    )
    def test_knowledge_curses_excluded_from_status_transform_options(self, status_id):
        card = make_card(status_id)
        options = transform_options_in_combat(card, character_pool=None)
        for bad in _CHOOSABLE_CURSE_IDS:
            assert bad not in options, (status_id, bad)
