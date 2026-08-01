"""
Tests for the engine features that unblock the remaining Ironclad cards:
combat history, in-combat card selection, X-costs, cards as hook listeners,
per-turn cost modifiers, and card-pool generation.

Run with:  py -m pytest test/test_engine_features.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import (
    BludgeonCard,
    Card,
    CardRarity,
    CardType,
    DefendCard,
    IRONCLAD_POOL,
    OneTwoPunchCard,
    StrikeCard,
    TargetType,
    TrueGritCard,
    make_card,
    pool_card_ids,
    random_pool_cards,
)
from sts2_rl.cmds import CardPileCmd, CardSelectCmd, ExhaustCmd
from sts2_rl.history import CardExhaustedEntry, CardPlayedEntry, DamageReceivedEntry
from sts2_rl.valueprops import DamageProps


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# Combat history
# ══════════════════════════════════════════════════════════════════════════

class TestCombatHistory:
    def test_card_exhausted_this_turn(self):
        cs = fresh()
        assert not cs.history.card_exhausted_this_turn()
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert cs.history.card_exhausted_this_turn()
        cs.end_turn()
        assert not cs.history.card_exhausted_this_turn()  # new turn

    def test_lost_hp_this_turn(self):
        cs = fresh()
        assert not cs.history.lost_hp_this_turn(cs.player)
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        assert cs.history.lost_hp_this_turn(cs.player)
        assert not cs.history.lost_hp_this_turn(cs.enemy)

    def test_enemy_turn_damage_does_not_count_next_turn(self):
        cs = fresh()
        cs.end_turn()  # any HP loss during the enemy phase is turn-1 history
        assert not cs.history.lost_hp_this_turn(cs.player)

    def test_times_damaged_counts_whole_combat_unblocked_only(self):
        cs = fresh()
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        cs.player.block = 10
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_UNPOWERED)
        assert cs.history.times_damaged(cs.player) == 2  # blocked hit excluded

    def test_attack_plays_this_turn(self):
        cs = fresh()
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        play(cs, DefendCard())
        assert cs.history.attack_plays_this_turn() == 2

    def test_doubled_attack_is_two_plays(self):
        """CardModel.cs:1904-1965 builds a fresh CardPlay per iteration and
        records History.CardPlayStarted (:1930) / CardPlayFinished (:1955)
        INSIDE the loop, so a doubled card is TWO plays in history, not one.

        This asserted 1 while the sim fired one hook bracket per logical play
        (hook_dispatch/G4); the entry's own note says the per-play entry count
        is deliberate in C# too and should follow the bracket.
        """
        cs = fresh()
        play(cs, OneTwoPunchCard())
        play(cs, StrikeCard())  # played twice => two CardPlay entries
        assert cs.history.attack_plays_this_turn() == 2


# ══════════════════════════════════════════════════════════════════════════
# Card selection
# ══════════════════════════════════════════════════════════════════════════

class TestCardSelection:
    def test_default_selector_is_random_from_candidates(self):
        cs = fresh()
        chosen = cs.select_cards("exhaust", list(cs.player.hand), 2)
        assert len(chosen) == 2
        assert all(c in cs.player.hand for c in chosen)

    def test_installed_selector_is_used(self):
        cs = fresh()
        target = cs.player.hand[3]
        cs.card_selector = lambda purpose, candidates, count: [target]
        assert cs.select_cards("exhaust", list(cs.player.hand), 1) == [target]

    def test_selector_results_outside_candidates_are_dropped(self):
        cs = fresh()
        rogue = StrikeCard()  # not among the candidates
        cs.card_selector = lambda purpose, candidates, count: [rogue]
        assert cs.select_cards("exhaust", list(cs.player.hand), 1) == []

    def test_from_hand_respects_predicate(self):
        cs = combat([StrikeCard(), StrikeCard(), DefendCard()])
        chosen = CardSelectCmd.from_hand(
            cs.hooks, cs.player, "upgrade", count=3,
            predicate=lambda c: c.card_type == CardType.ATTACK,
        )
        assert len(chosen) == 2
        assert all(c.card_type == CardType.ATTACK for c in chosen)

    def test_true_grit_upgraded_exhausts_chosen_card(self):
        cs = fresh()
        victim = cs.player.hand[0]
        cs.card_selector = lambda purpose, candidates, count: [victim]
        card = TrueGritCard()
        card.upgrade()
        play(cs, card)
        assert victim in cs.player.exhaust_pile


# ══════════════════════════════════════════════════════════════════════════
# CardSelectCmd's auto-select shortcut (creature_card_cmds/N10, step104,
# step105): `!RequireManualConfirmation && candidateCount <= MinSelect` ->
# every candidate, pile order, ZERO draws from any stream
# (CardSelectCmd.cs:287-290, 396-399, 708-711). C# checks this BEFORE
# consulting an installed Selector or the manual UI.
# ══════════════════════════════════════════════════════════════════════════

class TestCardSelectionAutoSelectShortcut:
    def test_full_candidate_selection_draws_nothing_from_either_rng(self):
        cs = fresh()
        candidates = list(cs.player.hand)  # 5 cards, requesting exactly 5
        legacy_state_before = cs._rng.getstate()
        parity_state_before = cs.combat_rng.card_selection.getstate()
        chosen = cs.select_cards("exhaust", candidates, len(candidates))
        assert cs._rng.getstate() == legacy_state_before
        assert cs.combat_rng.card_selection.getstate() == parity_state_before
        # Pile order preserved, not `random.sample`'s scrambled permutation.
        assert chosen == candidates

    def test_shortcut_also_fires_when_fewer_candidates_than_requested(self):
        # C#: `candidateCount <= MinSelect` — MinSelect defaults to the
        # requested count, so asking for 3 with only 2 candidates available
        # still auto-resolves (takes both, no screen).
        cs = fresh()
        candidates = [cs.player.hand[0], cs.player.hand[1]]
        state_before = cs._rng.getstate()
        chosen = cs.select_cards("exhaust", candidates, 3)
        assert cs._rng.getstate() == state_before
        assert chosen == candidates

    def test_shortcut_bypasses_an_installed_selector(self):
        # C#'s shortcut is checked BEFORE `else if (Selector != null)` — an
        # automated selector never even sees a full-candidate selection.
        cs = fresh()
        candidates = list(cs.player.hand)
        called = []
        cs.card_selector = lambda purpose, c, n: called.append(1) or list(c)[:n]
        chosen = cs.select_cards("exhaust", candidates, len(candidates))
        assert called == []
        assert chosen == candidates

    def test_below_threshold_selection_still_uses_the_selector(self):
        cs = fresh()
        candidates = list(cs.player.hand)
        target = candidates[0]
        cs.card_selector = lambda purpose, c, n: [target]
        chosen = cs.select_cards("exhaust", candidates, 1)
        assert chosen == [target]

    def test_below_threshold_selection_still_draws_from_the_legacy_rng(self):
        cs = fresh()
        candidates = list(cs.player.hand)
        state_before = cs._rng.getstate()
        cs.select_cards("exhaust", candidates, 1)
        assert cs._rng.getstate() != state_before

    def test_min_select_range_never_shortcuts_even_at_full_count(self):
        # A genuine MinSelect < MaxSelect range (RequireManualConfirmation =
        # true) never auto-resolves, however many candidates there are —
        # Ashwater/Gambler's Brew/Gambling Chip's `min_select=0` screens.
        cs = fresh()
        candidates = list(cs.player.hand)
        called = []
        cs.card_selector = lambda purpose, c, n: called.append(1) or list(c)
        cs.select_cards("exhaust_any", candidates, len(candidates), min_select=0)
        assert called == [1]

    def test_neows_fury_shaped_selection_does_not_shortcut_with_a_selector(self):
        # NeowsFury.cs:39 -- `new CardSelectorPrefs(prompt, 0, num)`, a
        # genuine 0..num RANGE (RequireManualConfirmation derives true,
        # CardSelectorPrefs.cs:77). With exactly `count` candidates in the
        # discard pile (the shape that used to coincide with the shortcut's
        # firing condition), the installed selector must still be consulted.
        cs = fresh()
        candidates = [cs.player.hand[0], cs.player.hand[1]]
        called = []
        cs.card_selector = lambda purpose, c, n: called.append(1) or list(c)
        chosen = cs.select_cards(
            "from_discard", candidates, len(candidates), min_select=0)
        assert called == [1]
        assert chosen == candidates

    def test_neows_fury_shaped_selection_without_a_selector_still_draws(self):
        cs = fresh()
        candidates = [cs.player.hand[0], cs.player.hand[1]]
        state_before = cs._rng.getstate()
        cs.select_cards("from_discard", candidates, len(candidates), min_select=0)
        assert cs._rng.getstate() != state_before

    def test_choose_a_card_shaped_selection_never_shortcuts(self):
        # CardSelectCmd.FromChooseACardScreen (CardSelectCmd.cs:216-261 --
        # Discovery/Splash, the four generator potions, Toolbox, Knowledge
        # Demon's curse pick) has NO CardSelectorPrefs/shortcut at all: with a
        # Selector installed it ALWAYS calls
        # `Selector.GetSelectedCards(cards, 0, 1)`, regardless of candidate
        # count. `has_shortcut=False` is how the sim callers for that C#
        # method opt out of the shortcut every other entry point shares.
        cs = fresh()
        candidates = [cs.player.hand[0]]  # exactly `count` candidates
        called = []
        cs.card_selector = lambda purpose, c, n: called.append(1) or list(c)[:n]
        chosen = cs.select_cards(
            "choose_a_card", candidates, 1, has_shortcut=False)
        assert called == [1]
        assert chosen == candidates

    def test_choose_a_card_shaped_selection_without_a_selector_still_draws(self):
        cs = fresh()
        candidates = [cs.player.hand[0]]
        state_before = cs._rng.getstate()
        cs.select_cards("choose_a_card", candidates, 1, has_shortcut=False)
        assert cs._rng.getstate() != state_before


class TestCardSelectionDrawPilePreSort:
    """CardSelectCmd.cs:403-408 — a DRAW pile is re-sorted `orderby c.Rarity,
    c.Id` before an installed Selector sees it (the manual UI screen sorts on
    its own, frontend side). `is_draw_pile=True` is the sim's opt-in — only
    FromCombatPile(Draw, ...) call sites (SecretTechnique/SecretWeapon,
    DropletOfPrecognition) pass it."""

    def _candidates(self):
        from sts2_rl.cards import make_card
        # BASIC(1): bash, defend, strike (id order); UNCOMMON(3): bludgeon;
        # EVENT(6): clash; STATUS(8): wound; CURSE(9): clumsy. Built
        # out-of-order on purpose so a passing test can't be a no-op.
        return [make_card(cid) for cid in
                ("clumsy", "wound", "clash", "bludgeon", "strike", "defend", "bash")]

    def test_draw_pile_candidates_are_sorted_for_the_selector(self):
        cs = fresh()
        seen = []
        cs.card_selector = lambda purpose, c, n: seen.append(list(c)) or list(c)[:n]
        candidates = self._candidates()
        cs.select_cards("from_draw", candidates, 1, is_draw_pile=True)
        assert [c.id for c in seen[0]] == [
            "bash", "defend", "strike", "bludgeon", "clash", "wound", "clumsy"]
        # The caller's own list is untouched.
        assert [c.id for c in candidates] == [
            "clumsy", "wound", "clash", "bludgeon", "strike", "defend", "bash"]

    def test_non_draw_pile_candidates_keep_pile_order(self):
        cs = fresh()
        seen = []
        cs.card_selector = lambda purpose, c, n: seen.append(list(c)) or list(c)[:n]
        candidates = self._candidates()
        cs.select_cards("from_discard", candidates, 1)  # is_draw_pile defaults False
        assert [c.id for c in seen[0]] == [c.id for c in candidates]

    def test_draw_pile_shortcut_returns_unsorted_pile_order(self):
        # C#'s shortcut (CardSelectCmd.cs:396-399) runs BEFORE the
        # `orderby Rarity, Id` pre-sort (:403-408), which sits inside the
        # `else if (Selector != null)` branch below it — a full-candidate
        # draw-pile selection never reaches the sort at all.
        cs = fresh()
        candidates = self._candidates()  # unsorted; count == len(candidates)
        chosen = cs.select_cards(
            "from_draw", candidates, len(candidates), is_draw_pile=True)
        assert [c.id for c in chosen] == [c.id for c in candidates]


# ══════════════════════════════════════════════════════════════════════════
# X-cost
# ══════════════════════════════════════════════════════════════════════════

class _XCostCard(Card):
    """Whirlwind-like test card: records the X it was played with."""
    id = "_x_test"
    name = "XTest"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF
    energy_cost_x = True

    def _init_vars(self) -> None:
        self.played_x = None

    def on_play(self, ctx, target_idx=None) -> None:
        self.played_x = self.captured_x


class TestXCost:
    def test_spends_all_energy_and_captures_x(self):
        cs = fresh()
        card = _XCostCard()
        play(cs, card, energy=3)
        assert card.played_x == 3
        assert cs.player.energy == 0

    def test_playable_at_zero_energy(self):
        cs = fresh()
        card = _XCostCard()
        cs.player.hand.append(card)
        cs.player.energy = 0
        assert (len(cs.player.hand) - 1) + 1 in cs.valid_actions()
        assert cs.play_card(len(cs.player.hand) - 1)
        assert card.played_x == 0

    def test_auto_play_captures_x_without_spending(self):
        cs = fresh()
        card = _XCostCard()
        cs.player.hand.append(card)
        cs.player.energy = 2
        cs.auto_play_card(card)
        assert card.played_x == 2
        assert cs.player.energy == 2


# ══════════════════════════════════════════════════════════════════════════
# Cards as hook listeners
# ══════════════════════════════════════════════════════════════════════════

class _DrumLikeCard(Card):
    """Drum of Battle-like test card: reacts to its own exhaustion."""
    id = "_drum_test"
    name = "DrumTest"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self.triggered = 0

    def on_play(self, ctx, target_idx=None) -> None:
        pass

    def on_card_exhausted(self, card,
                          caused_by_ethereal: bool = False) -> None:
        if card is self:
            self.triggered += 1


class TestCardsAsListeners:
    def test_starting_deck_cards_hear_hooks(self):
        drum = _DrumLikeCard()
        cs = combat([drum, DefendCard(), DefendCard()])
        ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
        assert drum.triggered == 1

    def test_generated_cards_are_registered(self):
        cs = fresh()
        drum = _DrumLikeCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, drum)
        ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
        assert drum.triggered == 1

    def test_auto_play_works_from_exhaust_pile(self):
        # Howl From Beyond replays itself from the exhaust pile at turn end.
        cs = fresh()
        strike = StrikeCard()
        cs.player.exhaust_pile.append(strike)
        before = cs.enemy.hp
        cs.auto_play_card(strike)
        assert cs.enemy.hp == before - 6
        assert strike in cs.player.discard_pile
        assert strike not in cs.player.exhaust_pile


# ══════════════════════════════════════════════════════════════════════════
# Per-turn cost modifiers
# ══════════════════════════════════════════════════════════════════════════

class TestTurnCostModifiers:
    def test_add_cost_this_turn_floors_at_zero_and_resets(self):
        cs = fresh()
        card = BludgeonCard()  # 3E
        cs.player.hand.append(card)
        card.add_cost_this_turn(-2)
        assert card.energy_cost == 1
        card.add_cost_this_turn(-2)
        assert card.energy_cost == 0
        cs.end_turn()
        assert card.energy_cost == 3  # reset at turn start

    def test_set_free_this_turn(self):
        cs = fresh()
        card = BludgeonCard()
        cs.player.hand.append(card)
        card.set_free_this_turn()
        assert card.energy_cost == 0
        cs.player.energy = 0
        assert cs.play_card(len(cs.player.hand) - 1)

    def test_free_this_turn_expires(self):
        cs = fresh()
        card = BludgeonCard()
        cs.player.hand.append(card)
        card.set_free_this_turn()
        cs.end_turn()
        assert card.energy_cost == 3


# ══════════════════════════════════════════════════════════════════════════
# Card-pool generation
# ══════════════════════════════════════════════════════════════════════════

class TestCardPool:
    def test_pool_ids_are_all_registered(self):
        for card_id in IRONCLAD_POOL:
            assert make_card(card_id).id == card_id

    def test_generation_excludes_basic_and_ancient(self):
        eligible = set(pool_card_ids(pool=IRONCLAD_POOL))
        assert "strike" not in eligible
        assert "defend" not in eligible
        assert "bash" not in eligible
        assert "break" not in eligible      # Ancient
        assert "corruption" not in eligible  # Ancient
        assert "bludgeon" in eligible

    def test_type_filter(self):
        rng = random.Random(0)
        cards = random_pool_cards(
            rng, 20, card_type=CardType.ATTACK, pool=IRONCLAD_POOL
        )
        assert len(cards) == 20
        assert all(c.card_type == CardType.ATTACK for c in cards)

    def test_distinct_generation(self):
        rng = random.Random(0)
        cards = random_pool_cards(rng, 15, distinct=True, pool=IRONCLAD_POOL)
        ids = [c.id for c in cards]
        assert len(ids) == len(set(ids)) == 15
