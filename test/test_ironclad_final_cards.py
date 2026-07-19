"""
Tests for the final batch of single-player Ironclad cards: the selection
cards (Armaments, Brand, Burning Pact, Headbutt), history cards (Evil Eye,
Forgotten Ritual, Spite, Tear Asunder, Stomp), X-cost cards (Whirlwind,
Cascade), card-hook cards (Drum of Battle, Howl From Beyond), and
pool-generation cards (Infernal Blade, Stoke).

Run with:  py -m pytest test/test_ironclad_final_cards.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd
from sts2_rl.cards import (
    ArmamentsCard,
    BrandCard,
    BurnCard,
    BurningPactCard,
    CardRarity,
    CardType,
    CascadeCard,
    DefendCard,
    DrumOfBattleCard,
    EvilEyeCard,
    ForgottenRitualCard,
    HeadbuttCard,
    HowlFromBeyondCard,
    InfernalBladeCard,
    SpiteCard,
    StokeCard,
    StompCard,
    StrikeCard,
    TearAsunderCard,
    WhirlwindCard,
)
from sts2_rl.cmds import CardPileCmd, ExhaustCmd
from sts2_rl.valueprops import DamageProps


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck, enemy HP 55–57)."""
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    """Combat whose starting deck is exactly `deck` (≤5 cards ⇒ all in hand)."""
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    """Give the player `card`, the given energy, and play it."""
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


def pick(*cards):
    """A card_selector that always chooses the given cards."""
    return lambda purpose, candidates, count: list(cards)


# ══════════════════════════════════════════════════════════════════════════
# Selection cards
# ══════════════════════════════════════════════════════════════════════════

class TestArmaments:
    def test_block_and_chosen_upgrade(self):
        cs = fresh()
        victim = cs.player.hand[0]
        cs.card_selector = pick(victim)
        play(cs, ArmamentsCard())
        assert cs.player.block == 5
        assert victim.upgrade_level == 1

    def test_upgraded_upgrades_all_upgradable_in_hand(self):
        cs = fresh()
        already = cs.player.hand[0]
        already.upgrade()
        burn = BurnCard()
        cs.player.hand.append(burn)
        card = ArmamentsCard()
        card.upgrade()
        play(cs, card)
        assert all(
            c.upgrade_level == 1 for c in cs.player.hand if c is not burn
        )
        assert already.upgrade_level == 1  # not upgraded twice
        assert burn.upgrade_level == 0  # statuses are never upgradable

    def test_statuses_are_not_upgradable(self):
        assert not BurnCard().is_upgradable
        assert StrikeCard().is_upgradable
        upgraded = StrikeCard()
        upgraded.upgrade()
        assert not upgraded.is_upgradable


class TestBrand:
    def test_hp_loss_is_unblockable_exhausts_chosen_and_gives_strength(self):
        cs = fresh()
        victim = cs.player.hand[0]
        cs.card_selector = pick(victim)
        cs.player.block = 5
        before = cs.player.hp
        play(cs, BrandCard())
        assert cs.player.hp == before - 1
        assert cs.player.block == 5  # HP loss ignores block
        assert victim in cs.player.exhaust_pile
        assert cs.player.powers["strength"].amount == 1

    def test_upgraded_gives_two_strength(self):
        cs = fresh()
        card = BrandCard()
        card.upgrade()
        play(cs, card)
        assert cs.player.powers["strength"].amount == 2


class TestBurningPact:
    def test_exhausts_chosen_and_draws(self):
        cs = fresh()
        victim = cs.player.hand[0]
        cs.card_selector = pick(victim)
        hand_before = len(cs.player.hand)
        play(cs, BurningPactCard())
        assert victim in cs.player.exhaust_pile
        # -1 exhausted, +2 drawn (played card left the hand it entered).
        assert len(cs.player.hand) == hand_before - 1 + 2

    def test_upgraded_draws_three(self):
        cs = fresh()
        cs.card_selector = pick(cs.player.hand[0])
        hand_before = len(cs.player.hand)
        card = BurningPactCard()
        card.upgrade()
        play(cs, card)
        assert len(cs.player.hand) == hand_before - 1 + 3


class TestHeadbutt:
    def test_damage_and_chosen_card_to_draw_top(self):
        cs = fresh()
        defend = DefendCard()
        cs.player.discard_pile.append(defend)
        cs.card_selector = pick(defend)
        before = cs.enemy.hp
        play(cs, HeadbuttCard())
        assert cs.enemy.hp == before - 9
        assert cs.player.draw_pile[-1] is defend  # top of the draw pile

    def test_cannot_choose_itself(self):
        cs = fresh()
        cs.player.discard_pile.clear()
        draw_before = list(cs.player.draw_pile)
        card = HeadbuttCard()
        play(cs, card)
        # Only itself was in the discard pile — nothing gets moved.
        assert cs.player.draw_pile == draw_before
        assert card in cs.player.discard_pile

    def test_upgrade_damage(self):
        cs = fresh()
        card = HeadbuttCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 12


# ══════════════════════════════════════════════════════════════════════════
# History cards
# ══════════════════════════════════════════════════════════════════════════

class TestEvilEye:
    def test_single_block_without_exhaust(self):
        cs = fresh()
        play(cs, EvilEyeCard())
        assert cs.player.block == 8

    def test_double_block_after_exhaust_this_turn(self):
        cs = fresh()
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        play(cs, EvilEyeCard())
        assert cs.player.block == 16

    def test_exhaust_last_turn_does_not_count(self):
        cs = fresh()
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        cs.end_turn()
        cs.player.block = 0
        play(cs, EvilEyeCard())
        assert cs.player.block == 8

    def test_upgrade_block(self):
        cs = fresh()
        card = EvilEyeCard()
        card.upgrade()
        play(cs, card)
        assert cs.player.block == 11


class TestForgottenRitual:
    def test_no_energy_without_exhaust_and_self_exhausts(self):
        cs = fresh()
        card = ForgottenRitualCard()
        play(cs, card, energy=10)
        assert cs.player.energy == 9  # cost 1, no payout
        assert card in cs.player.exhaust_pile

    def test_gains_energy_after_exhaust_this_turn(self):
        cs = fresh()
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        play(cs, ForgottenRitualCard(), energy=10)
        assert cs.player.energy == 12  # 10 - 1 + 3

    def test_first_ritual_enables_the_second(self):
        cs = fresh()
        play(cs, ForgottenRitualCard(), energy=10)  # exhausts itself
        play(cs, ForgottenRitualCard(), energy=10)
        assert cs.player.energy == 12

    def test_upgraded_gains_four(self):
        cs = fresh()
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        card = ForgottenRitualCard()
        card.upgrade()
        play(cs, card, energy=10)
        assert cs.player.energy == 13


class TestSpite:
    def test_single_hit_without_hp_loss(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, SpiteCard())
        assert cs.enemy.hp == before - 5

    def test_two_hits_after_losing_hp_this_turn(self):
        cs = fresh()
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        before = cs.enemy.hp
        play(cs, SpiteCard())
        assert cs.enemy.hp == before - 10

    def test_fully_blocked_damage_does_not_count(self):
        cs = fresh()
        cs.player.block = 10
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_UNPOWERED)
        before = cs.enemy.hp
        play(cs, SpiteCard())
        assert cs.enemy.hp == before - 5

    def test_upgraded_hits_three_times(self):
        cs = fresh()
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        card = SpiteCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 15


class TestTearAsunder:
    def test_base_single_hit(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, TearAsunderCard())
        assert cs.enemy.hp == before - 5

    def test_extra_hit_per_time_damaged_whole_combat(self):
        cs = fresh()
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        cs.end_turn()  # previous turns still count (whole-combat query)
        DamageCmd.deal(cs.hooks, cs.player, 3, props=DamageProps.NON_CARD_HP_LOSS)
        times = cs.history.times_damaged(cs.player)
        assert times >= 2  # the enemy turn may have added more
        before = cs.enemy.hp
        play(cs, TearAsunderCard())
        assert cs.enemy.hp == before - 5 * (1 + times)

    def test_upgrade_damage_per_hit(self):
        cs = fresh()
        card = TearAsunderCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 7


class TestStomp:
    def test_damage_all_enemies(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, StompCard())
        assert cs.enemy.hp == before - 12

    def test_discount_per_attack_played_and_reset(self):
        stomp = StompCard()
        deck = [stomp] + [DefendCard() for _ in range(4)]
        cs = combat(deck)
        assert stomp.energy_cost == 3
        play(cs, StrikeCard())
        assert stomp.energy_cost == 2
        play(cs, StrikeCard())
        assert stomp.energy_cost == 1
        play(cs, DefendCard())  # skills don't discount
        assert stomp.energy_cost == 1
        cs.end_turn()
        assert stomp.energy_cost == 3  # this-turn modifier expired

    def test_generated_stomp_seeds_from_history(self):
        cs = fresh()
        play(cs, StrikeCard())
        play(cs, StrikeCard())
        stomp = StompCard()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, stomp)
        assert stomp.energy_cost == 1

    def test_upgrade_damage(self):
        cs = fresh()
        card = StompCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 15


# ══════════════════════════════════════════════════════════════════════════
# X-cost cards
# ══════════════════════════════════════════════════════════════════════════

class TestWhirlwind:
    def test_hits_x_times(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, WhirlwindCard(), energy=3)
        assert cs.enemy.hp == before - 15
        assert cs.player.energy == 0

    def test_zero_energy_zero_hits(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, WhirlwindCard(), energy=0)
        assert cs.enemy.hp == before

    def test_upgrade_damage_per_hit(self):
        cs = fresh()
        card = WhirlwindCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card, energy=2)
        assert cs.enemy.hp == before - 16


class TestCascade:
    def test_auto_plays_top_x_cards(self):
        cs = fresh()
        s1, s2 = StrikeCard(), StrikeCard()
        cs.player.draw_pile.extend([s1, s2])  # s2 on top
        before = cs.enemy.hp
        play(cs, CascadeCard(), energy=2)
        assert cs.enemy.hp == before - 12
        assert s1 in cs.player.discard_pile
        assert s2 in cs.player.discard_pile
        assert cs.player.energy == 0

    def test_reshuffles_discard_when_draw_pile_empty(self):
        cs = fresh()
        strike = StrikeCard()
        cs.player.draw_pile.clear()
        cs.player.discard_pile[:] = [strike]
        before = cs.enemy.hp
        play(cs, CascadeCard(), energy=1)
        assert cs.enemy.hp == before - 6

    def test_stratagem_draining_the_reshuffled_pile_stops_the_pull(self):
        # Stratagem's on-shuffle fetch can empty the just-reshuffled draw
        # pile; Cascade then stops pulling (mirrors AutoPlayFromDrawPile's
        # null check after ShuffleIfNecessary).
        from sts2_rl.cmds import PowerCmd
        from sts2_rl.powers import StratagemPower

        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StratagemPower, 1)
        strike = StrikeCard()
        cs.player.draw_pile.clear()
        cs.player.discard_pile[:] = [strike]
        before = cs.enemy.hp
        play(cs, CascadeCard(), energy=1)
        assert strike in cs.player.hand  # fetched by Stratagem, not played
        assert cs.enemy.hp == before

    def test_upgraded_plays_x_plus_one(self):
        cs = fresh()
        cs.player.draw_pile.extend([StrikeCard(), StrikeCard()])
        card = CascadeCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card, energy=1)  # X=1, +1 upgraded → 2 plays
        assert cs.enemy.hp == before - 12


# ══════════════════════════════════════════════════════════════════════════
# Card-hook cards
# ══════════════════════════════════════════════════════════════════════════

class TestDrumOfBattle:
    def test_draws_two(self):
        cs = fresh()
        drum = DrumOfBattleCard()
        deck_hand = len(cs.player.hand)
        play(cs, drum)
        assert len(cs.player.hand) == deck_hand + 2

    def test_gains_energy_when_exhausted(self):
        drum = DrumOfBattleCard()
        cs = combat([drum] + [DefendCard() for _ in range(4)])
        cs.player.energy = 0
        ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
        assert cs.player.energy == 2

    def test_upgraded_gains_three(self):
        drum = DrumOfBattleCard()
        drum.upgrade()
        cs = combat([drum] + [DefendCard() for _ in range(4)])
        cs.player.energy = 0
        ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
        assert cs.player.energy == 3


class TestHowlFromBeyond:
    def test_damage_all_enemies(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, HowlFromBeyondCard())
        assert cs.enemy.hp == before - 16

    def test_replays_itself_from_exhaust_at_turn_end(self):
        howl = HowlFromBeyondCard()
        cs = combat([howl] + [DefendCard() for _ in range(4)])
        ExhaustCmd.exhaust(cs.hooks, cs.player, howl)
        before = cs.enemy.hp
        cs.end_turn()
        assert cs.enemy.hp == before - 16
        assert howl not in cs.player.exhaust_pile

    def test_stays_put_when_not_exhausted(self):
        howl = HowlFromBeyondCard()
        cs = combat([howl] + [DefendCard() for _ in range(4)])
        before = cs.enemy.hp
        cs.end_turn()
        assert cs.enemy.hp == before

    def test_upgrade_damage(self):
        cs = fresh()
        card = HowlFromBeyondCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 21


# ══════════════════════════════════════════════════════════════════════════
# Pool-generation cards
# ══════════════════════════════════════════════════════════════════════════

class TestInfernalBlade:
    def test_adds_free_attack_to_hand_and_exhausts(self):
        cs = fresh()
        card = InfernalBladeCard()
        play(cs, card)
        assert card in cs.player.exhaust_pile
        generated = cs.player.hand[-1]
        assert generated.card_type == CardType.ATTACK
        assert generated.energy_cost == 0  # free this turn
        assert generated.combat is cs  # registered as a hook listener

    def test_free_cost_expires_next_turn(self):
        cs = fresh()
        play(cs, InfernalBladeCard())
        generated = cs.player.hand[-1]
        cs.end_turn()
        assert not generated._free_this_turn

    def test_upgraded_costs_zero(self):
        cs = fresh()
        card = InfernalBladeCard()
        card.upgrade()
        play(cs, card, energy=0)


class TestStoke:
    def test_exhausts_hand_and_generates_that_many_pool_cards(self):
        cs = fresh()
        strike, defend = StrikeCard(), DefendCard()
        cs.player.hand[:] = [strike, defend]
        play(cs, StokeCard())
        assert strike in cs.player.exhaust_pile
        assert defend in cs.player.exhaust_pile
        assert len(cs.player.hand) == 2
        for card in cs.player.hand:
            assert card.rarity not in (CardRarity.BASIC, CardRarity.ANCIENT)
            assert card.combat is cs  # registered as a hook listener

    def test_empty_hand_generates_nothing(self):
        cs = fresh()
        cs.player.hand.clear()
        play(cs, StokeCard())
        assert len(cs.player.hand) == 0

    def test_upgraded_generates_upgraded_cards(self):
        cs = fresh()
        cs.player.hand[:] = [StrikeCard(), DefendCard()]
        card = StokeCard()
        card.upgrade()
        play(cs, card)
        assert all(c.upgrade_level == 1 for c in cs.player.hand)
