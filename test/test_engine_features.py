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

    def test_doubled_attack_is_one_play(self):
        cs = fresh()
        play(cs, OneTwoPunchCard())
        play(cs, StrikeCard())  # played twice, one card play
        assert cs.history.attack_plays_this_turn() == 1


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

    def on_card_exhausted(self, card) -> None:
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
        eligible = set(pool_card_ids())
        assert "strike" not in eligible
        assert "defend" not in eligible
        assert "bash" not in eligible
        assert "break" not in eligible      # Ancient
        assert "corruption" not in eligible  # Ancient
        assert "bludgeon" in eligible

    def test_type_filter(self):
        rng = random.Random(0)
        cards = random_pool_cards(rng, 20, card_type=CardType.ATTACK)
        assert len(cards) == 20
        assert all(c.card_type == CardType.ATTACK for c in cards)

    def test_distinct_generation(self):
        rng = random.Random(0)
        cards = random_pool_cards(rng, 15, distinct=True)
        ids = [c.id for c in cards]
        assert len(ids) == len(set(ids)) == 15
