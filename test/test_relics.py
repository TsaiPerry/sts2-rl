"""
Tests for the first 50 Ironclad-obtainable relics (sts2_rl/relics.py):
the alphabetical head of SharedRelicPool + IroncladRelicPool, Akabeko → Lantern.

Run with:  py -m pytest test/test_relics.py -v
"""
from __future__ import annotations

import random

from sts2_rl import (
    ALL_RELICS,
    CombatState,
    CreatureCmd,
    DamageCmd,
    make_relic,
)
from sts2_rl.cards import make_card
from sts2_rl.cmds import ExhaustCmd
from sts2_rl.relics import (
    Akabeko,
    Anchor,
    ArtOfWar,
    BagOfMarbles,
    BagOfPreparation,
    BeatingRemnant,
    Bellows,
    BeltBuckle,
    BloodVial,
    Bread,
    Brimstone,
    BronzeScales,
    BurningBlood,
    BurningSticks,
    Candelabra,
    CaptainsWheel,
    CentennialPuzzle,
    Chandelier,
    CharonsAshes,
    ChemicalX,
    CloakClasp,
    DemonTongue,
    FestivePopper,
    GamblingChip,
    GamePiece,
    GhostSeed,
    Girya,
    Gorget,
    GremlinHorn,
    HappyFlower,
    HornCleat,
    IceCream,
    IntimidatingHelmet,
    JossPaper,
    Kunai,
    Kusarigama,
    Lantern,
    # Newly implemented (SharedRelicPool tail + IroncladRelicPool)
    LetterOpener,
    LizardTail,
    MeatOnTheBone,
    MercuryHourglass,
    MiniatureCannon,
    MummifiedHand,
    Nunchaku,
    OddlySmoothStone,
    Orichalcum,
    OrnamentalFan,
    PaperPhrog,
    ParryingShield,
    PenNib,
    Pendulum,
    Permafrost,
    Pocketwatch,
    RainbowRing,
    RazorTooth,
    RedMask,
    RedSkull,
    ReptileTrinket,
    RingingTriangle,
    RippleBasin,
    RuinedHelmet,
    ScreamingFlagon,
    SelfFormingClay,
    Shuriken,
    SparklingRouge,
    StoneCalendar,
    StoneCracker,
    StrikeDummy,
    SturdyClamp,
    TheAbacus,
    TungstenRod,
    TuningFork,
    UnceasingTop,
    Vajra,
    Vambrace,
    VenerableTeaSet,
    VeryHotCocoa,
    VexingPuzzlebox,
)
from sts2_rl.potions import make_potion


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(relics=None, seed: int = 0, deck=None, **kwargs) -> CombatState:
    """Fresh combat with a fixed RNG seed and the given relics."""
    return CombatState(
        starting_deck=deck, rng=random.Random(seed), relics=relics, **kwargs
    )


def strikes(n: int) -> list:
    return [make_card("strike") for _ in range(n)]


def hand_index(cs: CombatState, card_id: str) -> int:
    for i, c in enumerate(cs.player.hand):
        if c.id == card_id:
            return i
    raise AssertionError(f"no {card_id} in hand: {cs.player.hand}")


# ══════════════════════════════════════════════════════════════════════════
# Registry / smoke
# ══════════════════════════════════════════════════════════════════════════

class TestRegistry:
    FIRST_50 = [
        "akabeko", "amethyst_aubergine", "anchor", "art_of_war",
        "bag_of_marbles", "bag_of_preparation", "beating_remnant", "bellows",
        "belt_buckle", "blood_vial", "book_of_five_rings", "bowler_hat",
        "bread", "brimstone", "bronze_scales", "burning_blood",
        "burning_sticks", "candelabra", "captains_wheel", "cauldron",
        "centennial_puzzle", "chandelier", "charons_ashes", "chemical_x",
        "cloak_clasp", "demon_tongue", "dingy_rug", "dollys_mirror",
        "dragon_fruit", "eternal_feather", "festive_popper", "fresnel_lens",
        "frozen_egg", "gambling_chip", "game_piece", "ghost_seed", "girya",
        "gnarled_hammer", "gorget", "gremlin_horn", "happy_flower",
        "horn_cleat", "ice_cream", "intimidating_helmet", "joss_paper",
        "juzu_bracelet", "kifuda", "kunai", "kusarigama", "lantern",
    ]

    def test_full_ironclad_pool_registered(self):
        # SharedRelicPool (118) + IroncladRelicPool (8) = 126 pool relics, plus
        # the event-granted Sword of Stone (Sunken Statue), the 7 Act-2 event
        # relics (Drowning Beacon's Fresnel Lens is already a pool relic; Trash
        # Heap's Darkstone Periapt / Dream Catcher / Hand Drill / Maw Bank / The
        # Boot, Colossal Flower's Pollinous Core, Lost Wisp), and the 4 Act-3
        # (Glory) event relics (Grave of the Forgotten's Forgotten Soul, Hungry
        # for Mushrooms' Big / Fragrant Mushroom, Round Tea Party's Royal Poison)
        # = 138, all constructible by id, and the original head is present.
        assert len(ALL_RELICS) == 138
        assert "sword_of_stone" in ALL_RELICS
        for eid in ("lost_wisp", "the_boot", "pollinous_core", "darkstone_periapt",
                    "dream_catcher", "hand_drill", "maw_bank",
                    "forgotten_soul", "big_mushroom", "fragrant_mushroom",
                    "royal_poison"):
            assert eid in ALL_RELICS
        for rid in ALL_RELICS:
            assert make_relic(rid).id == rid
        assert set(self.FIRST_50) <= set(ALL_RELICS)

    def test_full_pool_smoke_combat(self):
        # Attach every relic at once and play a whole combat at random —
        # nothing should crash and the combat should terminate.
        relics = [make_relic(rid) for rid in ALL_RELICS]
        cs = fresh(relics=relics, seed=7)
        rng = random.Random(7)
        for _ in range(200):
            if cs.is_over:
                break
            actions = cs.valid_actions()
            action = rng.choice(actions)
            if action == 0:
                cs.end_turn()
            else:
                cs.play_card(action - 1)
        assert cs.is_over


# ══════════════════════════════════════════════════════════════════════════
# Turn-1 / combat-start relics
# ══════════════════════════════════════════════════════════════════════════

class TestAkabeko:
    def test_vigor_boosts_first_attack_then_is_consumed(self):
        cs = fresh(relics=[Akabeko()], deck=strikes(9))
        assert cs.player.powers["vigor"].amount == 8
        before = cs.enemy.hp
        cs.play_card(0)
        assert cs.enemy.hp == before - 14  # 6 + 8 Vigor
        assert "vigor" not in cs.player.powers  # consumed by the attack
        before = cs.enemy.hp
        cs.play_card(0)
        assert cs.enemy.hp == before - 6  # back to base damage


class TestAnchor:
    def test_ten_block_at_combat_start(self):
        cs = fresh(relics=[Anchor()])
        assert cs.player.block == 10

    def test_block_does_not_return_on_turn_two(self):
        cs = fresh(relics=[Anchor()])
        cs.end_turn()
        assert cs.player.block == 0


class TestBagOfMarbles:
    def test_all_enemies_vulnerable_on_turn_one(self):
        cs = fresh(relics=[BagOfMarbles()], deck=strikes(9))
        assert all(e.powers["vulnerable"].amount == 1 for e in cs.enemies)
        before = cs.enemy.hp
        cs.play_card(0)
        assert cs.enemy.hp == before - 9  # 6 × 1.5


class TestBagOfPreparation:
    def test_draws_two_extra_on_turn_one_only(self):
        cs = fresh(relics=[BagOfPreparation()])
        assert len(cs.player.hand) == 7
        cs.end_turn()
        assert len(cs.player.hand) == 5


class TestBellows:
    def test_upgrades_opening_hand(self):
        cs = fresh(relics=[Bellows()])
        assert all(c.upgrade_level == 1 for c in cs.player.hand)
        assert all(c.upgrade_level == 0 for c in cs.player.draw_pile)


class TestBloodVial:
    def test_heals_two_at_combat_start(self):
        relic = BloodVial()
        cs = fresh(relics=[relic])
        cs.player.hp = 50
        relic.on_player_turn_started(cs.player)  # turn is still 1
        assert cs.player.hp == 52


class TestBronzeScales:
    def test_starts_with_three_thorns(self):
        cs = fresh(relics=[BronzeScales()])
        assert cs.player.powers["thorns"].amount == 3
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.enemy.hp == before - 3  # thorns reflection


class TestFestivePopper:
    def test_nine_damage_to_all_enemies_at_start(self):
        cs = fresh(relics=[FestivePopper()])
        for e in cs.enemies:
            assert e.hp == e.max_hp - 9

    def test_not_boosted_by_vulnerable(self):
        # Unpowered damage: Bag of Marbles' Vulnerable must not boost it.
        cs = fresh(relics=[BagOfMarbles(), FestivePopper()])
        for e in cs.enemies:
            assert e.hp == e.max_hp - 9


class TestGhostSeed:
    def test_basic_strikes_and_defends_are_ethereal(self):
        cs = fresh(relics=[GhostSeed()])
        basics = [c for c in cs.player.all_cards if c.id in ("strike", "defend")]
        assert basics and all(c.is_ethereal for c in basics)

    def test_unplayed_strikes_exhaust_at_turn_end(self):
        cs = fresh(relics=[GhostSeed()])
        hand_size = len(cs.player.hand)
        cs.end_turn()
        assert len(cs.player.exhaust_pile) == hand_size
        assert not cs.player.discard_pile


class TestGirya:
    def test_lifted_strength_at_combat_start(self):
        cs = fresh(relics=[Girya(times_lifted=3)])
        assert cs.player.powers["strength"].amount == 3

    def test_no_strength_without_lifts(self):
        cs = fresh(relics=[Girya()])
        assert "strength" not in cs.player.powers


class TestGorget:
    def test_plating_grants_block_at_turn_end(self):
        cs = fresh(relics=[Gorget()])
        assert cs.player.powers["plating"].amount == 4
        assert cs.player.block == 0  # no block until the turn ends
        cs.hooks.on_player_turn_end(cs.player)
        assert cs.player.block == 4


class TestGamblingChip:
    def test_mulligan_discards_and_redraws(self):
        # Selector mulligans exactly two named cards.
        def selector(purpose, candidates, count):
            assert purpose == "gambling_chip"
            return candidates[:2]

        cs = fresh(relics=[GamblingChip()], card_selector=selector)
        assert len(cs.player.hand) == 5
        assert len(cs.player.discard_pile) == 2

    def test_scripted_selector_only_mulligans_junk(self):
        from sts2_rl import scripted_card_selector
        deck = strikes(5) + [make_card("wound") for _ in range(4)]
        cs = fresh(
            relics=[GamblingChip()],
            deck=deck,
            card_selector=scripted_card_selector,
        )
        # Every Wound drawn into the opening hand was tossed and replaced.
        assert len(cs.player.hand) == 5
        assert all(c.id != "wound" for c in cs.player.hand) or not cs.player.draw_pile


# ══════════════════════════════════════════════════════════════════════════
# Energy relics
# ══════════════════════════════════════════════════════════════════════════

class TestEnergyRelics:
    def test_lantern_turn_one_energy(self):
        cs = fresh(relics=[Lantern()])
        assert cs.player.energy == 4
        cs.end_turn()
        assert cs.player.energy == 3

    def test_candelabra_turn_two_energy(self):
        cs = fresh(relics=[Candelabra()])
        assert cs.player.energy == 3
        cs.end_turn()
        assert cs.player.energy == 5

    def test_chandelier_turn_three_energy(self):
        cs = fresh(relics=[Chandelier()])
        cs.end_turn()
        assert cs.player.energy == 3
        cs.end_turn()
        assert cs.player.energy == 6

    def test_happy_flower_every_third_turn(self):
        cs = fresh(relics=[HappyFlower()])
        assert cs.player.energy == 3
        cs.end_turn()
        assert cs.player.energy == 3
        cs.end_turn()
        assert cs.player.energy == 4  # turn 3

    def test_bread_loses_two_on_turn_one_then_bonus(self):
        cs = fresh(relics=[Bread()])
        assert cs.player.energy == 1  # 3 − 2
        cs.end_turn()
        assert cs.player.energy == 4  # 3 + 1

    def test_ice_cream_conserves_energy(self):
        cs = fresh(relics=[IceCream()])
        assert cs.player.energy == 3
        cs.end_turn()
        assert cs.player.energy == 6  # 3 leftover + 3

    def test_art_of_war_rewards_attackless_turn(self):
        cs = fresh(relics=[ArtOfWar()], deck=strikes(9))
        cs.end_turn()  # no attacks on turn 1
        assert cs.player.energy == 4
        cs.play_card(0)  # attack on turn 2
        cs.end_turn()
        assert cs.player.energy == 3  # no bonus on turn 3


# ══════════════════════════════════════════════════════════════════════════
# Block relics
# ══════════════════════════════════════════════════════════════════════════

class TestBlockRelics:
    def test_horn_cleat_turn_two(self):
        cs = fresh(relics=[HornCleat()])
        assert cs.player.block == 0
        cs.end_turn()
        assert cs.player.block == 14

    def test_captains_wheel_turn_three(self):
        cs = fresh(relics=[CaptainsWheel()])
        cs.end_turn()
        assert cs.player.block == 0  # nothing on turn 2
        cs.end_turn()
        assert cs.player.block == 18

    def test_cloak_clasp_block_per_card_in_hand(self):
        cs = fresh(relics=[CloakClasp()])
        assert len(cs.player.hand) == 5
        cs.hooks.on_player_turn_end(cs.player)
        assert cs.player.block == 5

    def test_intimidating_helmet_two_cost_play(self):
        cs = fresh(relics=[IntimidatingHelmet()], deck=[make_card("bash")] + strikes(8))
        cs.play_card(hand_index(cs, "bash"))
        assert cs.player.block == 4
        cs.play_card(hand_index(cs, "strike"))  # 1-cost: no trigger
        assert cs.player.block == 4


# ══════════════════════════════════════════════════════════════════════════
# Damage-taken relics
# ══════════════════════════════════════════════════════════════════════════

class TestBeatingRemnant:
    def test_caps_hp_loss_at_twenty_per_turn(self):
        cs = fresh(relics=[BeatingRemnant()])
        DamageCmd.deal(cs.hooks, cs.player, 50, dealer=cs.enemy)
        assert cs.player.hp == cs.player.max_hp - 20
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy)
        assert cs.player.hp == cs.player.max_hp - 20  # allowance exhausted

    def test_allowance_resets_next_turn(self):
        cs = fresh(relics=[BeatingRemnant()])
        DamageCmd.deal(cs.hooks, cs.player, 50, dealer=cs.enemy)
        cs.end_turn()
        # Fresh 20-HP allowance on turn 2.
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 25, dealer=cs.enemy)
        assert cs.player.hp == before - 20

    def test_block_still_absorbs_first(self):
        cs = fresh(relics=[BeatingRemnant()])
        cs.player.block = 10
        DamageCmd.deal(cs.hooks, cs.player, 15, dealer=cs.enemy)
        assert cs.player.hp == cs.player.max_hp - 5


class TestCentennialPuzzle:
    def test_first_hp_loss_draws_three(self):
        cs = fresh(relics=[CentennialPuzzle()])
        assert len(cs.player.hand) == 5
        DamageCmd.deal(cs.hooks, cs.player, 4, dealer=cs.enemy)
        assert len(cs.player.hand) == 8
        DamageCmd.deal(cs.hooks, cs.player, 4, dealer=cs.enemy)
        assert len(cs.player.hand) == 8  # once per combat

    def test_fully_blocked_hit_does_not_trigger(self):
        cs = fresh(relics=[CentennialPuzzle()])
        cs.player.block = 10
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert len(cs.player.hand) == 5


class TestDemonTongue:
    def test_heals_own_turn_hp_loss_once_per_turn(self):
        cs = fresh(relics=[DemonTongue()])
        # Self-damage during the player's own turn (e.g. Hemokinesis).
        DamageCmd.deal(cs.hooks, cs.player, 6)
        assert cs.player.hp == cs.player.max_hp  # healed straight back
        DamageCmd.deal(cs.hooks, cs.player, 6)
        assert cs.player.hp == cs.player.max_hp - 6  # once per turn

    def test_enemy_turn_damage_does_not_trigger(self):
        cs = fresh(relics=[DemonTongue()])
        cs.current_side = "enemy"
        DamageCmd.deal(cs.hooks, cs.player, 6, dealer=cs.enemy)
        assert cs.player.hp == cs.player.max_hp - 6


# ══════════════════════════════════════════════════════════════════════════
# Exhaust relics
# ══════════════════════════════════════════════════════════════════════════

class TestBurningSticks:
    def test_first_exhausted_skill_is_copied_to_hand(self):
        deck = [make_card("defend") for _ in range(9)]
        cs = fresh(relics=[BurningSticks()], deck=deck)
        hand_size = len(cs.player.hand)
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert len(cs.player.hand) == hand_size  # −1 exhausted, +1 copy
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert len(cs.player.hand) == hand_size - 1  # once per combat

    def test_exhausted_attack_is_not_copied(self):
        cs = fresh(relics=[BurningSticks()], deck=strikes(9))
        hand_size = len(cs.player.hand)
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert len(cs.player.hand) == hand_size - 1

    def test_copy_keeps_upgrades(self):
        deck = [make_card("defend") for _ in range(9)]
        for c in deck:
            c.upgrade()
        cs = fresh(relics=[BurningSticks()], deck=deck)
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert all(c.upgrade_level == 1 for c in cs.player.hand)


class TestCharonsAshes:
    def test_three_damage_to_all_enemies_per_exhaust(self):
        cs = fresh(relics=[CharonsAshes()])
        before = [e.hp for e in cs.enemies]
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert [e.hp for e in cs.enemies] == [hp - 3 for hp in before]


class TestJossPaper:
    def test_draws_one_per_five_exhausts(self):
        cs = fresh(relics=[JossPaper()], deck=strikes(10))
        for _ in range(4):
            ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert len(cs.player.hand) == 1
        ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[0])
        assert len(cs.player.hand) == 1  # 5th exhaust drew a card


# ══════════════════════════════════════════════════════════════════════════
# Card-play relics
# ══════════════════════════════════════════════════════════════════════════

class TestGamePiece:
    def test_power_card_draws_one(self):
        deck = [make_card("inflame")] + strikes(8)
        cs = fresh(relics=[GamePiece()], deck=deck)
        hand_size = len(cs.player.hand)
        cs.play_card(hand_index(cs, "inflame"))
        assert len(cs.player.hand) == hand_size  # −1 played, +1 drawn


class TestChemicalX:
    def test_x_cost_cards_gain_two_x(self):
        deck = [make_card("whirlwind")] + strikes(8)
        cs = fresh(relics=[ChemicalX()], deck=deck)
        idx = hand_index(cs, "whirlwind")
        card = cs.player.hand[idx]
        before = [e.hp for e in cs.enemies]
        cs.play_card(idx)  # 3 energy → X = 5
        assert card.captured_x == 5
        assert cs.player.energy == 0
        assert all(hp - e.hp == 25 for hp, e in zip(before, cs.enemies))


class TestKunai:
    def test_dexterity_every_three_attacks(self):
        cs = fresh(relics=[Kunai()], deck=strikes(9))
        cs.play_card(0)
        cs.play_card(0)
        assert "dexterity" not in cs.player.powers
        cs.play_card(0)
        assert cs.player.powers["dexterity"].amount == 1

    def test_counter_resets_each_turn(self):
        cs = fresh(relics=[Kunai()], deck=strikes(20))
        cs.play_card(0)
        cs.play_card(0)
        cs.end_turn()
        cs.play_card(0)
        assert "dexterity" not in cs.player.powers


class TestKusarigama:
    def test_six_damage_every_three_attacks(self):
        cs = fresh(relics=[Kusarigama()], deck=strikes(9))
        total_before = sum(e.hp for e in cs.enemies)
        cs.play_card(0)
        cs.play_card(0)
        cs.play_card(0)
        # 3 strikes (18) + one 6-damage proc.
        assert total_before - sum(e.hp for e in cs.enemies) == 24


class TestBrimstone:
    def test_strength_ramp_each_turn(self):
        cs = fresh(relics=[Brimstone()])
        assert cs.player.powers["strength"].amount == 2
        assert all(e.powers["strength"].amount == 1 for e in cs.enemies)
        cs.end_turn()
        assert cs.player.powers["strength"].amount == 4
        assert all(e.powers["strength"].amount == 2 for e in cs.enemies)


# ══════════════════════════════════════════════════════════════════════════
# Potion / kill / victory relics
# ══════════════════════════════════════════════════════════════════════════

class TestBeltBuckle:
    def test_dexterity_when_potionless(self):
        cs = fresh(relics=[BeltBuckle()])
        assert cs.player.powers["dexterity"].amount == 2

    def test_no_dexterity_until_potions_are_gone(self):
        potions = [make_potion("block_potion")]
        cs = fresh(relics=[BeltBuckle()], potions=potions)
        assert "dexterity" not in cs.player.powers
        cs.use_potion(0)
        assert cs.player.powers["dexterity"].amount == 2


class TestGremlinHorn:
    def test_enemy_death_gives_energy_and_draw(self):
        from sts2_rl import NIBBITS_NORMAL
        cs = fresh(relics=[GremlinHorn()], deck=strikes(9), encounter=NIBBITS_NORMAL)
        assert len(cs.enemies) == 2
        hand_size = len(cs.player.hand)
        cs.enemy.hp = 1
        cs.play_card(0)
        assert not cs.is_over
        assert cs.player.energy == 3  # 3 − 1 strike + 1 horn
        assert len(cs.player.hand) == hand_size  # −1 played, +1 drawn


class TestBurningBlood:
    def test_heals_six_on_victory(self):
        cs = fresh(relics=[BurningBlood()], deck=strikes(9))
        cs.player.hp = 50
        for e in cs.enemies:
            e.hp = 1
        while not cs.is_over:
            cs.play_card(0)
        assert cs.result.player_won
        assert cs.player.hp == 56

    def test_no_heal_on_defeat(self):
        cs = fresh(relics=[BurningBlood()])
        cs.player.hp = 30
        CreatureCmd.kill(cs.hooks, cs.player)
        cs.hooks.on_combat_end(False)
        assert cs.player.hp <= 30


# ══════════════════════════════════════════════════════════════════════════
# Newly implemented relics (SharedRelicPool tail + IroncladRelicPool)
# ══════════════════════════════════════════════════════════════════════════

def power_card():
    """A Power-type card from the Ironclad pool (for type-triggered relics)."""
    return make_card("aggression")


class TestCombatStartRelics:
    def test_very_hot_cocoa_four_energy(self):
        base = fresh().player.energy
        assert fresh(relics=[VeryHotCocoa()]).player.energy == base + 4

    def test_oddly_smooth_stone_dexterity(self):
        assert fresh(relics=[OddlySmoothStone()]).player.powers["dexterity"].amount == 1

    def test_vajra_strength(self):
        assert fresh(relics=[Vajra()]).player.powers["strength"].amount == 1

    def test_red_mask_weakens_all(self):
        cs = fresh(relics=[RedMask()])
        assert all(e.powers["weak"].amount == 1 for e in cs.enemies)

    def test_mercury_hourglass_hits_all(self):
        cs = fresh(relics=[MercuryHourglass()])
        assert all(e.hp == e.max_hp - 3 for e in cs.enemies)

    def test_stone_cracker_upgrades_two(self):
        cs = fresh(relics=[StoneCracker()], deck=strikes(9))
        assert sum(c.upgrade_level for c in cs.player.all_cards) == 2

    def test_venerable_tea_set_only_when_rested(self):
        base = fresh().player.energy
        assert fresh(relics=[VenerableTeaSet(rested=True)]).player.energy == base + 2
        assert fresh(relics=[VenerableTeaSet(rested=False)]).player.energy == base

    def test_vexing_puzzlebox_adds_free_card(self):
        cs = fresh(relics=[VexingPuzzlebox()])
        assert len(cs.player.hand) == 6
        assert any(c.energy_cost == 0 for c in cs.player.hand)


class TestDamageBonusRelics:
    def test_strike_dummy_boosts_strikes(self):
        cs = fresh(relics=[StrikeDummy()], deck=strikes(9))
        before = cs.enemy.hp
        cs.play_card(hand_index(cs, "strike"))
        assert cs.enemy.hp == before - 9  # 6 + 3

    def test_miniature_cannon_only_upgraded(self):
        def upgraded_deck():
            d = strikes(9)
            for c in d:
                c.upgrade()
            return d
        base_cs = fresh(deck=upgraded_deck())
        b0 = base_cs.enemy.hp
        base_cs.play_card(hand_index(base_cs, "strike"))
        base_dmg = b0 - base_cs.enemy.hp

        cs = fresh(relics=[MiniatureCannon()], deck=upgraded_deck())
        b1 = cs.enemy.hp
        cs.play_card(hand_index(cs, "strike"))
        assert (b1 - cs.enemy.hp) == base_dmg + 3

        # unupgraded strike gets no bonus
        plain = fresh(relics=[MiniatureCannon()], deck=strikes(9))
        b2 = plain.enemy.hp
        plain.play_card(hand_index(plain, "strike"))
        assert plain.enemy.hp == b2 - 6

    def test_paper_phrog_boosts_vulnerable(self):
        cs = fresh(relics=[PaperPhrog(), BagOfMarbles()], deck=strikes(9))
        before = cs.enemy.hp
        cs.play_card(hand_index(cs, "strike"))
        assert cs.enemy.hp == before - 10  # int(6 * 1.75)


class TestPerTurnCounters:
    def test_letter_opener_three_skills(self):
        cs = fresh(relics=[LetterOpener()], deck=[make_card("defend") for _ in range(9)])
        before = cs.enemy.hp
        for _ in range(3):
            cs.play_card(hand_index(cs, "defend"))
        assert cs.enemy.hp == before - 5

    def test_ornamental_fan_three_attacks(self):
        cs = fresh(relics=[OrnamentalFan()], deck=strikes(9))
        for _ in range(3):
            cs.play_card(hand_index(cs, "strike"))
        assert cs.player.block == 4

    def test_shuriken_three_attacks(self):
        cs = fresh(relics=[Shuriken()], deck=strikes(9))
        for _ in range(3):
            cs.play_card(hand_index(cs, "strike"))
        assert cs.player.powers["strength"].amount == 1

    def test_rainbow_ring_all_three_types(self):
        relic = RainbowRing()
        cs = fresh(relics=[relic])
        relic.on_card_played(make_card("strike"))
        relic.on_card_played(make_card("defend"))
        assert "strength" not in cs.player.powers
        relic.on_card_played(power_card())
        assert cs.player.powers["strength"].amount == 1
        assert cs.player.powers["dexterity"].amount == 1


class TestCumulativeCounters:
    def test_nunchaku_ten_attacks(self):
        relic = Nunchaku()
        cs = fresh(relics=[relic])
        e0 = cs.player.energy
        for _ in range(9):
            relic.on_card_played(make_card("strike"))
        assert cs.player.energy == e0
        relic.on_card_played(make_card("strike"))
        assert cs.player.energy == e0 + 1

    def test_tuning_fork_ten_skills(self):
        relic = TuningFork()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        for _ in range(9):
            relic.on_card_played(make_card("defend"))
        assert cs.player.block == 0
        relic.on_card_played(make_card("defend"))
        assert cs.player.block == 7

    def test_pen_nib_tenth_attack_doubled(self):
        relic = PenNib()
        cs = fresh(relics=[relic])
        cards = [make_card("strike") for _ in range(10)]
        for c in cards[:9]:
            relic.before_card_played(c)
            assert relic.modify_damage_multiplicative(cs.enemy, 6, cs.player, c) == 1.0
            relic.on_card_played(c)
        relic.before_card_played(cards[9])
        assert relic.modify_damage_multiplicative(cs.enemy, 6, cs.player, cards[9]) == 2.0
        assert relic.modify_damage_multiplicative(cs.enemy, 6, cs.player, cards[0]) == 1.0
        relic.on_card_played(cards[9])
        assert relic.modify_damage_multiplicative(cs.enemy, 6, cs.player, cards[9]) == 1.0


class TestTurnEndRelics:
    def test_orichalcum_block_when_bare(self):
        relic = Orichalcum()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        relic.on_player_turn_end(cs.player)
        assert cs.player.block == 6

    def test_orichalcum_no_block_when_blocking(self):
        relic = Orichalcum()
        cs = fresh(relics=[relic])
        cs.player.block = 5
        relic.on_player_turn_end(cs.player)
        assert cs.player.block == 5

    def test_parrying_shield_needs_ten_block(self):
        relic = ParryingShield()
        cs = fresh(relics=[relic])
        cs.player.block = 10
        before = cs.enemy.hp
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == before - 6
        cs.player.block = 5
        again = cs.enemy.hp
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == again

    def test_screaming_flagon_empty_hand(self):
        relic = ScreamingFlagon()
        cs = fresh(relics=[relic])
        cs.player.hand = []
        before = cs.enemy.hp
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == before - 20

    def test_screaming_flagon_no_damage_with_cards(self):
        relic = ScreamingFlagon()
        cs = fresh(relics=[relic])
        before = cs.enemy.hp
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == before

    def test_ripple_basin_no_attacks(self):
        relic = RippleBasin()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        relic.on_player_turn_end(cs.player)
        assert cs.player.block == 4

    def test_ripple_basin_after_attack(self):
        relic = RippleBasin()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        relic.on_card_played(make_card("strike"))
        relic.on_player_turn_end(cs.player)
        assert cs.player.block == 0

    def test_stone_calendar_turn_seven(self):
        relic = StoneCalendar()
        cs = fresh(relics=[relic])
        cs.turn = 6
        before = cs.enemy.hp
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == before
        cs.turn = 7
        relic.on_player_turn_end(cs.player)
        assert cs.enemy.hp == before - 52


class TestDefensiveRelics:
    def test_tungsten_rod_reduces_hp_loss(self):
        cs = fresh(relics=[TungstenRod()])
        cs.player.block = 0
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy)
        assert cs.player.hp == 80 - 9

    def test_lizard_tail_prevents_death_once(self):
        cs = fresh(relics=[LizardTail()])
        cs.player.block = 0
        DamageCmd.deal(cs.hooks, cs.player, 200, dealer=cs.enemy)
        assert not cs.player.is_dead
        assert cs.player.hp == 41  # reset to 1, then healed 50% of 80
        DamageCmd.deal(cs.hooks, cs.player, 200, dealer=cs.enemy)
        assert cs.player.is_dead

    def test_self_forming_clay_block_next_turn(self):
        relic = SelfFormingClay()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.block == 0  # not yet
        relic.on_player_turn_started(cs.player)
        assert cs.player.block == 6  # 3 per HP-loss event

    def test_vambrace_doubles_first_card_block(self):
        cs = fresh(relics=[Vambrace()], deck=[make_card("defend") for _ in range(9)])
        cs.play_card(hand_index(cs, "defend"))
        assert cs.player.block == 10  # 5 x2
        cs.play_card(hand_index(cs, "defend"))
        assert cs.player.block == 15  # +5 normal

    def test_sturdy_clamp_caps_retained_block(self):
        relic = SturdyClamp()
        cs = fresh(relics=[relic])
        assert relic.should_clear_block(cs.player) is False
        cs.player.block = 25
        relic.on_player_turn_start(cs.player)
        assert cs.player.block == 10
        cs.player.block = 6
        relic.on_player_turn_start(cs.player)
        assert cs.player.block == 6

    def test_the_abacus_block_on_shuffle(self):
        relic = TheAbacus()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        relic.on_shuffle(cs.player)
        assert cs.player.block == 6


class TestStrengthRelics:
    def test_ruined_helmet_doubles_first_strength(self):
        cs = fresh(relics=[RuinedHelmet(), Vajra()])
        assert cs.player.powers["strength"].amount == 2  # Vajra 1, doubled

    def test_ruined_helmet_only_first(self):
        from sts2_rl.cmds import PowerCmd
        from sts2_rl.powers import StrengthPower
        cs = fresh(relics=[RuinedHelmet(), Vajra()])
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.player)
        assert cs.player.powers["strength"].amount == 5  # 2 + 3 (not doubled)

    def test_reptile_trinket_strength_on_potion(self):
        relic = ReptileTrinket()
        cs = fresh(relics=[relic])
        relic.on_potion_used(None, None)
        assert cs.player.powers["strength"].amount == 3

    def test_red_skull_below_half(self):
        cs = fresh(relics=[RedSkull()])
        assert "strength" not in cs.player.powers
        DamageCmd.deal(cs.hooks, cs.player, 45, dealer=cs.enemy)  # 80 -> 35
        assert cs.player.powers["strength"].amount == 3

    def test_red_skull_removed_when_healed(self):
        cs = fresh(relics=[RedSkull()])
        DamageCmd.deal(cs.hooks, cs.player, 45, dealer=cs.enemy)
        assert cs.player.powers["strength"].amount == 3
        CreatureCmd.heal(cs.hooks, cs.player, 20)  # 35 -> 55
        assert "strength" not in cs.player.powers

    def test_sparkling_rouge_turn_three(self):
        relic = SparklingRouge()
        cs = fresh(relics=[relic])
        cs.turn = 3
        relic.on_player_turn_started(cs.player)
        assert cs.player.powers["strength"].amount == 1
        assert cs.player.powers["dexterity"].amount == 1


class TestCardManipulationRelics:
    def test_permafrost_first_power_blocks(self):
        relic = Permafrost()
        cs = fresh(relics=[relic])
        cs.player.block = 0
        relic.on_card_played(power_card())
        assert cs.player.block == 7
        relic.on_card_played(power_card())
        assert cs.player.block == 7  # only the first
        relic.on_card_played(make_card("strike"))
        assert cs.player.block == 7  # not a power

    def test_mummified_hand_frees_a_card(self):
        relic = MummifiedHand()
        cs = fresh(relics=[relic], deck=strikes(9))
        relic.on_card_played(power_card())
        assert any(c.energy_cost == 0 for c in cs.player.hand)

    def test_razor_tooth_upgrades_played_attack(self):
        cs = fresh(relics=[RazorTooth()], deck=strikes(9))
        idx = hand_index(cs, "strike")
        strike = cs.player.hand[idx]
        assert strike.upgrade_level == 0
        cs.play_card(idx)
        assert strike.upgrade_level == 1

    def test_pendulum_draws_every_three_turns(self):
        relic = Pendulum()
        cs = fresh()
        relic.combat = cs
        h0 = len(cs.player.hand)
        relic.on_player_turn_started(cs.player)
        relic.on_player_turn_started(cs.player)
        assert len(cs.player.hand) == h0
        relic.on_player_turn_started(cs.player)
        assert len(cs.player.hand) == h0 + 1

    def test_pocketwatch_extra_draw_after_light_turn(self):
        relic = Pocketwatch()
        cs = fresh(relics=[relic])
        cs.turn = 2
        relic._played_last_turn = 2
        assert relic.modify_hand_draw(cs.player, 5) == 8
        relic._played_last_turn = 4
        assert relic.modify_hand_draw(cs.player, 5) == 5

    def test_pocketwatch_no_bonus_turn_one(self):
        relic = Pocketwatch()
        cs = fresh(relics=[relic])
        cs.turn = 1
        relic._played_last_turn = 0
        assert relic.modify_hand_draw(cs.player, 5) == 5

    def test_unceasing_top_draws_on_empty_hand(self):
        relic = UnceasingTop()
        cs = fresh(relics=[relic], deck=strikes(9))
        cs.player.hand = []
        relic.on_card_played(make_card("strike"))
        assert len(cs.player.hand) == 1

    def test_unceasing_top_no_draw_with_cards(self):
        relic = UnceasingTop()
        cs = fresh(relics=[relic], deck=strikes(9))
        n = len(cs.player.hand)
        relic.on_card_played(make_card("strike"))
        assert len(cs.player.hand) == n

    def test_ringing_triangle_retains_turn_one_hand(self):
        cs = fresh(relics=[RingingTriangle()], deck=strikes(15))
        turn1 = list(cs.player.hand)
        cs.end_turn()
        for c in turn1:
            assert c in cs.player.hand
        assert len(cs.player.hand) > len(turn1)

    def test_ringing_triangle_flushes_later_turns(self):
        cs = fresh(relics=[RingingTriangle()], deck=strikes(15))
        cs.end_turn()  # turn 2: turn-1 hand retained
        turn2 = list(cs.player.hand)
        cs.end_turn()  # turn 3: normal flush
        assert not all(c in cs.player.hand for c in turn2)


class TestCombatEndRelics:
    def test_meat_on_the_bone_heals_when_low(self):
        cs = fresh(relics=[MeatOnTheBone()], deck=strikes(9))
        cs.player.hp = 30
        for e in cs.enemies:
            e.hp = 1
        while not cs.is_over:
            cs.play_card(0)
        assert cs.player.hp == 42

    def test_meat_on_the_bone_no_heal_when_high(self):
        cs = fresh(relics=[MeatOnTheBone()], deck=strikes(9))
        cs.player.hp = 60
        for e in cs.enemies:
            e.hp = 1
        while not cs.is_over:
            cs.play_card(0)
        assert cs.player.hp == 60
