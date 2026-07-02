"""
Tests for the Ironclad cards in sts2_rl/cards/.

Run with:  python -m pytest test/test_ironclad_cards.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import (
    AngerCard,
    AshenStrikeCard,
    BarricadeCard,
    BashCard,
    BloodWallCard,
    BloodlettingCard,
    BludgeonCard,
    BodySlamCard,
    BreakCard,
    BullyCard,
    CinderCard,
    ConflagrationCard,
    DarkEmbraceCard,
    DefendCard,
    DemonFormCard,
    DismantleCard,
    DominateCard,
    FeedCard,
    FeelNoPainCard,
    FiendFireCard,
    FightMeCard,
    GiantRockCard,
    HavocCard,
    HemokinesisCard,
    ImperviousCard,
    InflameCard,
    IronWaveCard,
    MoltenFistCard,
    NotYetCard,
    OfferingCard,
    PactsEndCard,
    PerfectedStrikeCard,
    PillageCard,
    PommelStrikeCard,
    RampageCard,
    RuptureCard,
    SecondWindCard,
    ShrugItOffCard,
    StrikeCard,
    SwordBoomerangCard,
    TauntCard,
    ThrashCard,
    ThunderclapCard,
    TrembleCard,
    TrueGritCard,
    TwinStrikeCard,
    UppercutCard,
    WoundCard,
    make_card,
)
from sts2_rl.powers import FeelNoPainPower, VulnerablePower


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck, enemy HP 55–57)."""
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    """Combat whose starting deck is exactly `deck` (≤5 cards ⇒ all in hand)."""
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    """Give the player `card`, plenty of energy, and play it."""
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# Engine additions: Exhaust keyword, power cards leaving play
# ══════════════════════════════════════════════════════════════════════════

class TestExhaustKeyword:
    def test_exhaust_card_goes_to_exhaust_pile(self):
        cs = fresh()
        card = ImperviousCard()
        play(cs, card)
        assert card in cs.player.exhaust_pile
        assert card not in cs.player.discard_pile

    def test_exhaust_keyword_triggers_feel_no_pain(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, FeelNoPainPower, 3)
        play(cs, TrembleCard())
        assert cs.player.block == 3

    def test_non_exhaust_card_goes_to_discard(self):
        cs = fresh()
        card = BludgeonCard()
        play(cs, card)
        assert card in cs.player.discard_pile


class TestPowerCardRemoval:
    def test_power_card_leaves_all_piles_when_played(self):
        cs = fresh()
        card = InflameCard()
        play(cs, card)
        assert card not in cs.player.all_cards


# ══════════════════════════════════════════════════════════════════════════
# Attacks
# ══════════════════════════════════════════════════════════════════════════

class TestAnger:
    def test_damage_and_clone_to_discard(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, AngerCard())
        assert cs.enemy.hp == before - 6
        angers = [c for c in cs.player.discard_pile if isinstance(c, AngerCard)]
        assert len(angers) == 2  # the played card + the clone

    def test_clone_keeps_upgrade_level(self):
        cs = fresh()
        card = AngerCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 8
        clone = [c for c in cs.player.discard_pile if isinstance(c, AngerCard) and c is not card][0]
        assert clone.upgrade_level == 1


class TestAshenStrike:
    def test_scales_with_exhaust_pile(self):
        cs = fresh()
        cs.player.exhaust_pile = [WoundCard(), WoundCard()]
        before = cs.enemy.hp
        play(cs, AshenStrikeCard())
        assert cs.enemy.hp == before - 12  # 6 + 3×2

    def test_base_damage_with_empty_exhaust_pile(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, AshenStrikeCard())
        assert cs.enemy.hp == before - 6


class TestBash:
    def test_damage_and_vulnerable(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, BashCard())
        assert cs.enemy.hp == before - 8
        assert cs.enemy.powers["vulnerable"].amount == 2


class TestBludgeon:
    def test_damage(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, BludgeonCard())
        assert cs.enemy.hp == before - 32


class TestBodySlam:
    def test_damage_equals_block(self):
        cs = fresh()
        cs.player.block = 12
        before = cs.enemy.hp
        play(cs, BodySlamCard())
        assert cs.enemy.hp == before - 12

    def test_zero_block_deals_nothing(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, BodySlamCard())
        assert cs.enemy.hp == before

    def test_upgrade_reduces_cost_to_zero(self):
        card = BodySlamCard()
        card.upgrade()
        assert card.energy_cost == 0


class TestBreak:
    def test_damage_and_vulnerable(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, BreakCard())
        assert cs.enemy.hp == before - 20
        assert cs.enemy.powers["vulnerable"].amount == 5


class TestBully:
    def test_scales_with_target_vulnerable(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3)
        before = cs.enemy.hp
        play(cs, BullyCard())
        # (4 + 2×3) × 1.5 (Vulnerable) = 15
        assert cs.enemy.hp == before - 15

    def test_base_damage_without_vulnerable(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, BullyCard())
        assert cs.enemy.hp == before - 4


class TestCinder:
    def test_damage_and_random_hand_exhaust(self):
        cs = combat([CinderCard(), DefendCard()])
        cinder = [c for c in cs.player.hand if isinstance(c, CinderCard)][0]
        defend = [c for c in cs.player.hand if isinstance(c, DefendCard)][0]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(cinder))
        assert cs.enemy.hp == before - 18
        assert defend in cs.player.exhaust_pile


class TestConflagration:
    def test_hits_each_enemy_four_times(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, ConflagrationCard())
        assert cs.enemy.hp == before - 8  # 2 × 4 hits

    def test_upgrade_adds_a_hit(self):
        cs = fresh()
        card = ConflagrationCard()
        card.upgrade()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 10


class TestDismantle:
    def test_single_hit_without_vulnerable(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, DismantleCard())
        assert cs.enemy.hp == before - 8

    def test_double_hit_when_vulnerable(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 1)
        before = cs.enemy.hp
        play(cs, DismantleCard())
        assert cs.enemy.hp == before - 24  # 2 × int(8 × 1.5)


class TestFeed:
    def test_fatal_grants_max_hp_and_heals(self):
        cs = fresh()
        cs.enemy.hp = 5
        cs.player.hp = 70
        card = FeedCard()
        play(cs, card)
        assert cs.enemy.is_dead
        assert cs.player.max_hp == 83
        assert cs.player.hp == 73
        assert card in cs.player.exhaust_pile

    def test_no_max_hp_without_kill(self):
        cs = fresh()
        play(cs, FeedCard())
        assert cs.player.max_hp == 80


class TestFiendFire:
    def test_exhausts_hand_and_hits_per_card(self):
        cs = combat([FiendFireCard(), WoundCard(), DefendCard(), StrikeCard()])
        ff = [c for c in cs.player.hand if isinstance(c, FiendFireCard)][0]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(ff))
        assert cs.enemy.hp == before - 21  # 3 cards exhausted × 7
        assert cs.player.hand == []
        assert len(cs.player.exhaust_pile) == 4  # 3 hand cards + Fiend Fire itself


class TestFightMe:
    def test_hits_and_strength_for_both_sides(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, FightMeCard())
        assert cs.enemy.hp == before - 10  # 5 × 2
        assert cs.player.strength == 3
        assert cs.enemy.strength == 1


class TestHemokinesis:
    def test_hp_loss_and_damage(self):
        cs = fresh()
        p_before, e_before = cs.player.hp, cs.enemy.hp
        play(cs, HemokinesisCard())
        assert cs.player.hp == p_before - 2
        assert cs.enemy.hp == e_before - 15

    def test_hp_loss_ignores_block(self):
        cs = fresh()
        cs.player.block = 10
        p_before = cs.player.hp
        play(cs, HemokinesisCard())
        assert cs.player.hp == p_before - 2
        assert cs.player.block == 10


class TestIronWave:
    def test_block_and_damage(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, IronWaveCard())
        assert cs.player.block == 5
        assert cs.enemy.hp == before - 5


class TestMoltenFist:
    def test_doubles_target_vulnerable(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        before = cs.enemy.hp
        card = MoltenFistCard()
        play(cs, card)
        assert cs.enemy.hp == before - 15  # int(10 × 1.5)
        assert cs.enemy.powers["vulnerable"].amount == 4
        assert card in cs.player.exhaust_pile

    def test_no_vulnerable_applied_when_target_has_none(self):
        cs = fresh()
        play(cs, MoltenFistCard())
        assert "vulnerable" not in cs.enemy.powers


class TestPactsEnd:
    def test_no_damage_below_three_exhausted(self):
        cs = fresh()
        cs.player.exhaust_pile = [WoundCard(), WoundCard()]
        before = cs.enemy.hp
        play(cs, PactsEndCard())
        assert cs.enemy.hp == before

    def test_damage_with_three_exhausted(self):
        cs = fresh()
        cs.player.exhaust_pile = [WoundCard(), WoundCard(), WoundCard()]
        before = cs.enemy.hp
        play(cs, PactsEndCard())
        assert cs.enemy.hp == before - 17


class TestPerfectedStrike:
    def test_counts_strike_tagged_cards_in_all_piles(self):
        cs = combat([PerfectedStrikeCard()])
        cs.player.draw_pile = [StrikeCard(), StrikeCard()]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(0)
        # itself + 2 Strikes = 3 tagged cards → 6 + 2×3 = 12
        assert cs.enemy.hp == before - 12


class TestPillage:
    def test_draws_until_non_attack(self):
        cs = combat([PillageCard()])
        # draw pile pops from the end: Strike, Strike, Defend
        cs.player.draw_pile = [DefendCard(), StrikeCard(), StrikeCard()]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(0)
        assert cs.enemy.hp == before - 6
        assert len(cs.player.hand) == 3
        assert isinstance(cs.player.hand[-1], DefendCard)


class TestPommelStrike:
    def test_damage_and_draw(self):
        cs = combat([PommelStrikeCard()])
        cs.player.draw_pile = [DefendCard()]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(0)
        assert cs.enemy.hp == before - 9
        assert len(cs.player.hand) == 1


class TestRampage:
    def test_damage_grows_each_play(self):
        cs = fresh()
        card = RampageCard()
        before = cs.enemy.hp
        play(cs, card)
        assert cs.enemy.hp == before - 9
        assert card._damage == 14
        before = cs.enemy.hp
        cs.player.discard_pile.remove(card)
        play(cs, card)
        assert cs.enemy.hp == before - 14


class TestSwordBoomerang:
    def test_three_hits_on_random_enemies(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, SwordBoomerangCard())
        assert cs.enemy.hp == before - 9  # 3 × 3 on the only enemy


class TestThrash:
    def test_two_hits_and_absorbs_exhausted_attack_damage(self):
        cs = combat([ThrashCard(), StrikeCard()])
        thrash = [c for c in cs.player.hand if isinstance(c, ThrashCard)][0]
        strike = [c for c in cs.player.hand if isinstance(c, StrikeCard)][0]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(thrash))
        assert cs.enemy.hp == before - 8  # 4 × 2
        assert strike in cs.player.exhaust_pile
        assert thrash._damage == 10  # 4 + Strike's 6


class TestThunderclap:
    def test_damage_and_vulnerable_to_all(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, ThunderclapCard())
        assert cs.enemy.hp == before - 4
        assert cs.enemy.powers["vulnerable"].amount == 1


class TestTwinStrike:
    def test_two_hits(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, TwinStrikeCard())
        assert cs.enemy.hp == before - 10


class TestUppercut:
    def test_damage_weak_and_vulnerable(self):
        cs = fresh()
        before = cs.enemy.hp
        play(cs, UppercutCard())
        assert cs.enemy.hp == before - 13
        assert cs.enemy.powers["weak"].amount == 1
        assert cs.enemy.powers["vulnerable"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# Skills
# ══════════════════════════════════════════════════════════════════════════

class TestBloodWall:
    def test_hp_loss_then_block(self):
        cs = fresh()
        before = cs.player.hp
        play(cs, BloodWallCard())
        assert cs.player.hp == before - 2
        assert cs.player.block == 16


class TestBloodletting:
    def test_hp_loss_and_energy(self):
        cs = fresh()
        before = cs.player.hp
        play(cs, BloodlettingCard(), energy=3)
        assert cs.player.hp == before - 3
        assert cs.player.energy == 5  # 3 - 0 cost + 2


class TestDominate:
    def test_strength_equals_target_vulnerable_after_apply(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        card = DominateCard()
        play(cs, card)
        assert cs.enemy.powers["vulnerable"].amount == 3
        assert cs.player.strength == 3
        assert card in cs.player.exhaust_pile


class TestHavoc:
    def test_plays_top_of_draw_pile_and_exhausts_it(self):
        cs = combat([HavocCard()])
        strike = StrikeCard()
        cs.player.draw_pile = [strike]
        before = cs.enemy.hp
        cs.player.energy = 10
        assert cs.play_card(0)
        assert cs.enemy.hp == before - 6
        assert strike in cs.player.exhaust_pile

    def test_unplayable_card_exhausted_without_playing(self):
        cs = combat([HavocCard()])
        wound = WoundCard()
        cs.player.draw_pile = [wound]
        cs.player.energy = 10
        assert cs.play_card(0)
        assert wound in cs.player.exhaust_pile

    def test_no_crash_with_empty_piles(self):
        cs = combat([HavocCard()])
        cs.player.draw_pile = []
        cs.player.energy = 10
        assert cs.play_card(0)


class TestImpervious:
    def test_block(self):
        cs = fresh()
        play(cs, ImperviousCard())
        assert cs.player.block == 30


class TestNotYet:
    def test_heal_and_exhaust(self):
        cs = fresh()
        cs.player.hp = 50
        card = NotYetCard()
        play(cs, card)
        assert cs.player.hp == 60
        assert card in cs.player.exhaust_pile


class TestOffering:
    def test_hp_energy_and_draw(self):
        cs = combat([OfferingCard()])
        cs.player.draw_pile = [StrikeCard(), StrikeCard(), StrikeCard(), StrikeCard()]
        before = cs.player.hp
        cs.player.energy = 3
        assert cs.play_card(0)
        assert cs.player.hp == before - 6
        assert cs.player.energy == 5
        assert len(cs.player.hand) == 3


class TestPrimalForce:
    def test_transforms_attacks_into_giant_rocks(self):
        cs = combat([make_card("primal_force"), StrikeCard(), DefendCard()])
        pf = [c for c in cs.player.hand if c.id == "primal_force"][0]
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(pf))
        assert any(isinstance(c, GiantRockCard) for c in cs.player.hand)
        assert not any(isinstance(c, StrikeCard) for c in cs.player.hand)
        assert any(isinstance(c, DefendCard) for c in cs.player.hand)

    def test_upgraded_creates_upgraded_rocks(self):
        cs = combat([make_card("primal_force"), StrikeCard()])
        pf = [c for c in cs.player.hand if c.id == "primal_force"][0]
        pf.upgrade()
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(pf))
        rock = [c for c in cs.player.hand if isinstance(c, GiantRockCard)][0]
        assert rock.upgrade_level == 1


class TestSecondWind:
    def test_exhausts_non_attacks_for_block(self):
        cs = combat([SecondWindCard(), WoundCard(), DefendCard(), StrikeCard()])
        sw = [c for c in cs.player.hand if isinstance(c, SecondWindCard)][0]
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(sw))
        assert cs.player.block == 10  # 2 non-attacks × 5
        assert len(cs.player.exhaust_pile) == 2
        assert all(isinstance(c, StrikeCard) for c in cs.player.hand)


class TestShrugItOff:
    def test_block_and_draw(self):
        cs = combat([ShrugItOffCard()])
        cs.player.draw_pile = [StrikeCard()]
        cs.player.energy = 10
        assert cs.play_card(0)
        assert cs.player.block == 8
        assert len(cs.player.hand) == 1


class TestTaunt:
    def test_block_and_vulnerable(self):
        cs = fresh()
        play(cs, TauntCard())
        assert cs.player.block == 7
        assert cs.enemy.powers["vulnerable"].amount == 1


class TestTremble:
    def test_vulnerable_and_exhaust(self):
        cs = fresh()
        card = TrembleCard()
        play(cs, card)
        assert cs.enemy.powers["vulnerable"].amount == 3
        assert card in cs.player.exhaust_pile


class TestTrueGrit:
    def test_block_and_random_exhaust(self):
        cs = combat([TrueGritCard(), DefendCard()])
        tg = [c for c in cs.player.hand if isinstance(c, TrueGritCard)][0]
        defend = [c for c in cs.player.hand if isinstance(c, DefendCard)][0]
        cs.player.energy = 10
        assert cs.play_card(cs.player.hand.index(tg))
        assert cs.player.block == 7
        assert defend in cs.player.exhaust_pile


# ══════════════════════════════════════════════════════════════════════════
# Powers
# ══════════════════════════════════════════════════════════════════════════

class TestPowerCards:
    def test_barricade(self):
        cs = fresh()
        play(cs, BarricadeCard())
        assert "barricade" in cs.player.powers

    def test_barricade_upgrade_reduces_cost(self):
        card = BarricadeCard()
        card.upgrade()
        assert card.energy_cost == 2

    def test_dark_embrace(self):
        cs = fresh()
        play(cs, DarkEmbraceCard())
        assert "dark_embrace" in cs.player.powers

    def test_demon_form(self):
        cs = fresh()
        play(cs, DemonFormCard())
        assert cs.player.powers["demon_form"].amount == 2

    def test_feel_no_pain(self):
        cs = fresh()
        play(cs, FeelNoPainCard())
        assert cs.player.powers["feel_no_pain"].amount == 3

    def test_inflame(self):
        cs = fresh()
        play(cs, InflameCard())
        assert cs.player.strength == 2

    def test_rupture_upgraded_gives_two_strength_per_hp_loss(self):
        cs = fresh()
        card = RuptureCard()
        card.upgrade()
        play(cs, card)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.strength == 2
