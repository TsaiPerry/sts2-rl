"""
Tests for the Hive (parallel Act 2) enemies and their powers (Imbalanced,
Hard to Kill, Tender, Hatch, Slumber, Escape Artist, Flutter, Swipe,
Burrowed, Reattach, Personal Hive, Vital Spark/Tainted, Crab Rage,
Surrounded, Sandpit, and the Knowledge Demon curses).

Run with:  py -m pytest test/test_hive.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.afflictions import TaintedAffliction
from sts2_rl.cards import CardRarity, make_card
from sts2_rl.monsters import Encounter, MoveType
from sts2_rl.monsters.hive import (
    BowlbugEgg,
    BowlbugNectar,
    BowlbugRock,
    BowlbugSilk,
    Chomper,
    Crusher,
    Entomancer,
    Exoskeleton,
    HunterKiller,
    InfestedPrism,
    KnowledgeDemon,
    LouseProgenitor,
    Myte,
    Ovicopter,
    Parafright,
    Rocket,
    SlumberingBeetle,
    SpinyToad,
    TheInsatiable,
    TheObscura,
    ThievingHopper,
    ToughEgg,
    Tunneler,
    BOWLBUGS_NORMAL,
    BOWLBUGS_WEAK,
    CHOMPERS_NORMAL,
    DECIMILLIPEDE_ELITE,
    ENCOUNTERS,
    EXOSKELETONS_NORMAL,
    EXOSKELETONS_WEAK,
    KAISER_CRAB_BOSS,
    MYTES_NORMAL,
    SLUMBERING_BEETLE_NORMAL,
    THE_INSATIABLE_BOSS,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


def fresh_encounter(enc: Encounter, seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed), encounter=enc)


# ═════════════════════════════════════════════════════════════════════════
# Bowlbugs
# ═════════════════════════════════════════════════════════════════════════

class TestBowlbugs:
    def test_hp_ranges(self):
        for seed in range(10):
            assert 45 <= fresh_with(BowlbugRock, seed).enemy.max_hp <= 48
            assert 21 <= fresh_with(BowlbugEgg, seed).enemy.max_hp <= 22
            assert 40 <= fresh_with(BowlbugSilk, seed).enemy.max_hp <= 43
            assert 35 <= fresh_with(BowlbugNectar, seed).enemy.max_hp <= 38

    def test_rock_headbutts_every_turn(self):
        cs = fresh_with(BowlbugRock)
        cs.end_turn()
        assert cs.player.hp == 80 - 15
        cs.end_turn()
        assert cs.player.hp == 80 - 30

    def test_rock_imbalanced_by_full_block(self):
        cs = fresh_with(BowlbugRock)
        rock = cs.enemy
        assert "imbalanced" in rock.powers
        cs.player.block = 20
        cs.end_turn()  # HEADBUTT fully blocked -> off balance
        assert cs.player.hp == 80
        assert rock.is_off_balance
        assert rock.current_intent.move_type == MoveType.STUN
        cs.end_turn()  # DIZZY: loses the turn
        assert cs.player.hp == 80
        assert not rock.is_off_balance
        cs.end_turn()  # back to HEADBUTT
        assert cs.player.hp == 80 - 15

    def test_rock_partial_block_keeps_balance(self):
        cs = fresh_with(BowlbugRock)
        cs.player.block = 10
        cs.end_turn()  # 15 - 10 block = 5 through
        assert cs.player.hp == 75
        assert not cs.enemy.is_off_balance

    def test_egg_bites_and_blocks(self):
        cs = fresh_with(BowlbugEgg)
        egg = cs.enemy
        cs.end_turn()
        assert cs.player.hp == 80 - 7
        assert egg.block == 7

    def test_silk_opens_with_weak_spit(self):
        cs = fresh_with(BowlbugSilk)
        cs.end_turn()  # TOXIC_SPIT: Weak 1
        assert cs.player.hp == 80
        assert cs.player.powers["weak"].amount == 1  # first tick skipped
        cs.end_turn()  # THRASH 4x2
        assert cs.player.hp == 80 - 8

    def test_nectar_buffs_once_then_thrashes(self):
        cs = fresh_with(BowlbugNectar)
        nectar = cs.enemy
        cs.end_turn()  # THRASH 3
        assert cs.player.hp == 77
        cs.end_turn()  # BUFF: +15 Strength
        assert cs.player.hp == 77
        assert nectar.strength == 15
        cs.end_turn()  # THRASH2 3 + 15
        assert cs.player.hp == 77 - 18
        cs.end_turn()  # THRASH2 repeats
        assert cs.player.hp == 77 - 36

    def test_weak_encounter_composition(self):
        seen = set()
        for seed in range(10):
            cs = fresh_encounter(BOWLBUGS_WEAK, seed)
            assert len(cs.enemies) == 2
            assert isinstance(cs.enemies[0], BowlbugRock)
            assert isinstance(cs.enemies[1], (BowlbugEgg, BowlbugNectar))
            seen.add(type(cs.enemies[1]))
        assert seen == {BowlbugEgg, BowlbugNectar}

    def test_normal_encounter_two_distinct_workers(self):
        for seed in range(10):
            cs = fresh_encounter(BOWLBUGS_NORMAL, seed)
            assert len(cs.enemies) == 3
            assert isinstance(cs.enemies[0], BowlbugRock)
            worker_types = [type(e) for e in cs.enemies[1:]]
            assert len(set(worker_types)) == 2
            for t in worker_types:
                assert t in (BowlbugEgg, BowlbugSilk, BowlbugNectar)


# ═════════════════════════════════════════════════════════════════════════
# Chompers
# ═════════════════════════════════════════════════════════════════════════

class TestChompers:
    def test_encounter_second_screams_first(self):
        cs = fresh_encounter(CHOMPERS_NORMAL)
        first, second = cs.enemies
        for chomper in cs.enemies:
            assert 60 <= chomper.max_hp <= 64
            assert chomper.powers["artifact"].amount == 2
        assert first._current_move.id == "CLAMP_MOVE"
        assert second._current_move.id == "SCREECH_MOVE"

    def test_clamp_and_screech(self):
        cs = fresh_encounter(CHOMPERS_NORMAL)
        cs.end_turn()  # CLAMP 8x2 + SCREECH (3 Dazed to discard)
        assert cs.player.hp == 80 - 16
        assert sum(1 for c in cs.player.all_cards if c.id == "dazed") == 3
        cs.end_turn()  # SCREECH + CLAMP (they alternate)
        assert cs.player.hp == 80 - 32
        assert sum(1 for c in cs.player.all_cards if c.id == "dazed") == 6

    def test_artifact_blocks_two_debuffs(self):
        cs = fresh_encounter(CHOMPERS_NORMAL)
        chomper = cs.enemies[0]
        from sts2_rl.powers import VulnerablePower
        PowerCmd.apply(cs.hooks, chomper, VulnerablePower, 2)
        PowerCmd.apply(cs.hooks, chomper, VulnerablePower, 2)
        assert "vulnerable" not in chomper.powers
        assert "artifact" not in chomper.powers
        PowerCmd.apply(cs.hooks, chomper, VulnerablePower, 2)
        assert "vulnerable" in chomper.powers


# ═════════════════════════════════════════════════════════════════════════
# Exoskeletons
# ═════════════════════════════════════════════════════════════════════════

class TestExoskeletons:
    def test_slot_openers(self):
        cs = fresh_encounter(EXOSKELETONS_WEAK)
        assert [e._current_move.id for e in cs.enemies] == [
            "SKITTER_MOVE", "MANDIBLES_MOVE", "ENRAGE_MOVE",
        ]
        cs4 = fresh_encounter(EXOSKELETONS_NORMAL)
        assert len(cs4.enemies) == 4
        assert cs4.enemies[3]._current_move.id in ("SKITTER_MOVE", "MANDIBLES_MOVE")

    def test_first_turn_damage(self):
        cs = fresh_encounter(EXOSKELETONS_WEAK)
        third = cs.enemies[2]
        cs.end_turn()  # skitter 1x3 + mandibles 8 + enrage
        assert cs.player.hp == 80 - 3 - 8
        assert third.strength == 2

    def test_hard_to_kill_caps_hits_at_nine(self):
        cs = fresh_with(Exoskeleton)
        exo = cs.enemy
        assert 24 <= exo.max_hp <= 28
        assert exo.powers["hard_to_kill"].amount == 9
        DamageCmd.deal(cs.hooks, exo, 30, dealer=cs.player)
        assert exo.hp == exo.max_hp - 9
        DamageCmd.deal(cs.hooks, exo, 30, dealer=cs.player)
        assert exo.hp == exo.max_hp - 18

    def test_mandibles_chains_into_enrage(self):
        cs = fresh_with(Exoskeleton)  # slot "first": SKITTER opener
        exo = cs.enemy
        moves = []
        for _ in range(10):
            moves.append(exo._current_move.id)
            cs.player.hp = 80
            cs.end_turn()
        for a, b in zip(moves, moves[1:]):
            if a == "MANDIBLES_MOVE":
                assert b == "ENRAGE_MOVE"
            assert not (a == b == "SKITTER_MOVE")
            assert not (a == b == "MANDIBLES_MOVE")


# ═════════════════════════════════════════════════════════════════════════
# Hunter Killer
# ═════════════════════════════════════════════════════════════════════════

class TestHunterKiller:
    def test_goop_applies_tender(self):
        cs = fresh_with(HunterKiller)
        assert cs.enemy.max_hp == 121
        cs.end_turn()  # TENDERIZING_GOOP
        assert cs.player.hp == 80
        assert "tender" in cs.player.powers

    def test_tender_saps_strength_per_card(self):
        cs = fresh_with(HunterKiller)
        cs.end_turn()  # Tender 1 on the player
        played = 0
        for action in list(cs.valid_actions()):
            if action != 0 and played < 2:
                if cs.play_card(action - 1):
                    played += 1
        assert played == 2
        assert cs.player.powers["strength"].amount == -2
        assert cs.player.powers["dexterity"].amount == -2
        cs.end_turn()  # restored at turn end (stacks to 0 -> removed)
        assert "strength" not in cs.player.powers
        assert "dexterity" not in cs.player.powers

    def test_never_bites_twice_in_a_row(self):
        for seed in range(20):
            cs = fresh_with(HunterKiller, seed)
            hk = cs.enemy
            moves = []
            for _ in range(12):
                moves.append(hk._current_move.id)
                cs.player.hp = 80
                cs.end_turn()
            for a, b in zip(moves, moves[1:]):
                assert not (a == b == "BITE_MOVE")


# ═════════════════════════════════════════════════════════════════════════
# Louse Progenitor
# ═════════════════════════════════════════════════════════════════════════

class TestLouseProgenitor:
    def test_cycle(self):
        cs = fresh_with(LouseProgenitor)
        louse = cs.enemy
        assert 134 <= louse.max_hp <= 136
        cs.end_turn()  # WEB_CANNON 9 + Frail 2
        assert cs.player.hp == 80 - 9
        assert cs.player.powers["frail"].amount == 2
        cs.end_turn()  # CURL_AND_GROW: 14 block + 5 Strength
        assert louse.block == 14
        assert louse.strength == 5
        cs.end_turn()  # POUNCE 14 + 5
        assert cs.player.hp == 80 - 9 - 19
        cs.end_turn()  # WEB_CANNON 9 + 5
        assert cs.player.hp == 80 - 9 - 19 - 14

    def test_curl_up_blocks_on_first_hit(self):
        cs = fresh_with(LouseProgenitor)
        louse = cs.enemy
        assert louse.powers["curl_up"].amount == 14
        DamageCmd.deal(cs.hooks, louse, 5, dealer=cs.player)
        assert louse.hp == louse.max_hp - 5  # the triggering hit lands first
        assert louse.block == 14
        assert "curl_up" not in louse.powers


# ═════════════════════════════════════════════════════════════════════════
# Mytes
# ═════════════════════════════════════════════════════════════════════════

class TestMytes:
    def test_encounter_openers(self):
        cs = fresh_encounter(MYTES_NORMAL)
        first, second = cs.enemies
        for myte in cs.enemies:
            assert 61 <= myte.max_hp <= 67
        assert first._current_move.id == "TOXIC_MOVE"
        assert second._current_move.id == "SUCK_MOVE"

    def test_toxic_cards_hurt_in_hand(self):
        cs = fresh_encounter(MYTES_NORMAL)
        second = cs.enemies[1]
        cs.end_turn()  # TOXIC (2 Toxic into hand) + SUCK 4 (+2 Str)
        assert cs.player.hp == 80 - 4
        assert second.strength == 2
        toxics = [c for c in cs.player.hand if c.id == "toxic"]
        assert len(toxics) == 2
        # Left in hand: each Toxic deals 5 at turn end, then BITE 13 + TOXIC.
        cs.end_turn()
        assert cs.player.hp == 80 - 4 - 10 - 13

    def test_toxic_card_is_playable_and_exhausts(self):
        cs = fresh_encounter(MYTES_NORMAL)
        cs.end_turn()
        toxic = next(c for c in cs.player.hand if c.id == "toxic")
        assert cs.play_card(cs.player.hand.index(toxic))
        assert toxic in cs.player.exhaust_pile


# ═════════════════════════════════════════════════════════════════════════
# Ovicopter + Tough Eggs
# ═════════════════════════════════════════════════════════════════════════

class TestOvicopter:
    def test_lays_three_minion_eggs(self):
        cs = fresh_with(Ovicopter)
        assert 124 <= cs.enemy.max_hp <= 130
        cs.end_turn()  # LAY_EGGS
        assert cs.player.hp == 80
        eggs = [e for e in cs.enemies if isinstance(e, ToughEgg)]
        assert len(eggs) == 3
        for egg in eggs:
            assert 14 <= egg.max_hp <= 18
            assert "minion" in egg.powers
            assert egg.powers["hatch"].amount == 2
            assert egg.current_intent.move_type == MoveType.SUMMON

    def test_eggs_hatch_then_nibble(self):
        cs = fresh_with(Ovicopter)
        cs.end_turn()  # LAY_EGGS
        eggs = [e for e in cs.enemies if isinstance(e, ToughEgg)]
        cs.end_turn()  # SMASH 16; eggs hatch (no damage from them yet)
        assert cs.player.hp == 80 - 16
        for egg in eggs:
            assert egg.is_hatched
            assert 19 <= egg.max_hp <= 22
            assert egg.hp == egg.max_hp
            assert "hatch" not in egg.powers
            assert "minion" in egg.powers  # Minion survives the hatch
            assert egg.current_intent.move_type == MoveType.ATTACK

    def test_paste_while_eggs_alive_lay_after_they_die(self):
        cs = fresh_with(Ovicopter)
        ovi = cs.enemies[0]
        cs.end_turn()  # LAY_EGGS
        cs.player.hp = 80
        cs.end_turn()  # SMASH; eggs hatch
        cs.player.hp = 80
        cs.end_turn()  # TENDERIZER; 4 alive -> next is NUTRITIONAL_PASTE
        assert ovi._current_move.id == "NUTRITIONAL_PASTE_MOVE"
        assert not ovi._can_lay()
        for egg in [e for e in cs.enemies if isinstance(e, ToughEgg)]:
            DamageCmd.deal(cs.hooks, egg, 99, dealer=cs.player)
        assert ovi._can_lay()

    def test_minion_eggs_do_not_prolong_combat(self):
        cs = fresh_with(Ovicopter)
        cs.end_turn()  # LAY_EGGS
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        assert cs._all_enemies_dead()


# ═════════════════════════════════════════════════════════════════════════
# Slumbering Beetle
# ═════════════════════════════════════════════════════════════════════════

class TestSlumberingBeetle:
    def test_encounter_composition(self):
        cs = fresh_encounter(SLUMBERING_BEETLE_NORMAL)
        assert isinstance(cs.enemies[0], BowlbugRock)
        assert isinstance(cs.enemies[1], BowlbugSilk)
        assert isinstance(cs.enemies[2], SlumberingBeetle)

    def test_starts_asleep_with_plating_block(self):
        cs = fresh_with(SlumberingBeetle)
        beetle = cs.enemy
        assert beetle.max_hp == 86
        assert beetle.powers["plating"].amount == 15
        assert beetle.powers["slumber"].amount == 3
        assert beetle.block == 15
        assert beetle.current_intent.move_type == MoveType.SLEEP

    def test_natural_wake_after_three_turns(self):
        cs = fresh_with(SlumberingBeetle)
        beetle = cs.enemy
        for _ in range(3):
            cs.end_turn()
            assert cs.player.hp == 80
        assert beetle.is_awake
        assert "slumber" not in beetle.powers
        assert "plating" not in beetle.powers
        assert not beetle.stunned
        intent = beetle.current_intent
        assert intent.move_type == MoveType.ATTACK and intent.damage == 16
        cs.end_turn()  # ROLL_OUT 16 (+2 Str after)
        assert cs.player.hp == 80 - 16
        assert beetle.strength == 2
        cs.end_turn()  # ROLL_OUT 16 + 2
        assert cs.player.hp == 80 - 16 - 18

    def test_three_unblocked_hits_wake_it_stunned(self):
        cs = fresh_with(SlumberingBeetle)
        beetle = cs.enemy
        DamageCmd.deal(cs.hooks, beetle, 20, dealer=cs.player)  # 15 blocked, 5 in
        assert beetle.powers["slumber"].amount == 2
        DamageCmd.deal(cs.hooks, beetle, 5, dealer=cs.player)
        DamageCmd.deal(cs.hooks, beetle, 5, dealer=cs.player)
        assert "slumber" not in beetle.powers
        assert beetle.is_awake
        assert "plating" not in beetle.powers
        assert beetle.stunned
        assert beetle.current_intent.move_type == MoveType.STUN
        cs.end_turn()  # wake-up turn: nothing
        assert cs.player.hp == 80
        cs.end_turn()  # ROLL_OUT 16
        assert cs.player.hp == 80 - 16

    def test_fully_blocked_hits_do_not_count(self):
        cs = fresh_with(SlumberingBeetle)
        beetle = cs.enemy
        DamageCmd.deal(cs.hooks, beetle, 5, dealer=cs.player)  # absorbed by 15 block
        assert beetle.powers["slumber"].amount == 3


# ═════════════════════════════════════════════════════════════════════════
# Spiny Toad
# ═════════════════════════════════════════════════════════════════════════

class TestSpinyToad:
    def test_cycle_and_thorns(self):
        cs = fresh_with(SpinyToad)
        toad = cs.enemy
        assert 116 <= toad.max_hp <= 119
        cs.end_turn()  # PROTRUDING_SPIKES: +5 Thorns
        assert cs.player.hp == 80
        assert toad.powers["thorns"].amount == 5
        hp = cs.player.hp
        DamageCmd.deal(cs.hooks, toad, 1, dealer=cs.player)
        assert cs.player.hp == hp - 5  # thorns reflect
        cs.player.hp = 80
        cs.end_turn()  # SPIKE_EXPLOSION 23, thorns spent
        assert cs.player.hp == 80 - 23
        assert "thorns" not in toad.powers
        cs.end_turn()  # TONGUE_LASH 17
        assert cs.player.hp == 80 - 23 - 17
        assert toad._current_move.id == "PROTRUDING_SPIKES_MOVE"


# ═════════════════════════════════════════════════════════════════════════
# The Obscura + Parafright
# ═════════════════════════════════════════════════════════════════════════

class TestTheObscura:
    def test_summons_parafright_first(self):
        cs = fresh_with(TheObscura)
        assert cs.enemy.max_hp == 123
        cs.end_turn()  # ILLUSION (the new Parafright acts from next turn)
        assert cs.player.hp == 80
        para = cs.enemies[1]
        assert isinstance(para, Parafright)
        assert para.max_hp == 21
        assert "illusion" in para.powers
        assert "minion" in para.powers

    def test_parafright_revives_instead_of_dying(self):
        cs = fresh_with(TheObscura)
        cs.end_turn()
        para = cs.enemies[1]
        DamageCmd.deal(cs.hooks, para, 999, dealer=cs.player)
        illusion = para.powers["illusion"]
        assert illusion.is_reviving
        assert para.current_intent.move_type == MoveType.HEAL
        # Unhittable while reviving.
        assert DamageCmd.deal(cs.hooks, para, 10, dealer=cs.player) == 0
        cs.player.hp = 80
        cs.end_turn()  # revive turn
        assert para.hp == para.max_hp
        assert not illusion.is_reviving

    def test_killing_obscura_wins_despite_parafright(self):
        cs = fresh_with(TheObscura)
        cs.end_turn()
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        assert cs._all_enemies_dead()

    def test_never_repeats_after_summon(self):
        for seed in range(10):
            cs = fresh_with(TheObscura, seed)
            obscura = cs.enemy
            moves = []
            for _ in range(10):
                moves.append(obscura._current_move.id)
                cs.player.hp = 80
                cs.end_turn()
            assert moves[0] == "ILLUSION_MOVE"
            for a, b in zip(moves[1:], moves[2:]):
                assert a != b

    def test_wail_buffs_all_allies(self):
        cs = fresh_with(TheObscura)
        obscura = cs.enemies[0]
        cs.end_turn()  # summon
        para = cs.enemies[1]
        obscura._wail(cs._ctx())
        assert obscura.strength == 3
        assert para.strength == 3


# ═════════════════════════════════════════════════════════════════════════
# Thieving Hopper
# ═════════════════════════════════════════════════════════════════════════

class TestThievingHopper:
    def test_thievery_steals_a_card(self):
        cs = fresh_with(ThievingHopper)
        hopper = cs.enemy
        assert hopper.max_hp == 79
        assert hopper.powers["escape_artist"].amount == 5
        total_before = len(cs.player.all_cards)
        cs.end_turn()  # THIEVERY: steal + 17
        assert cs.player.hp == 80 - 17
        assert len(cs.player.all_cards) == total_before - 1
        assert len(hopper.powers["swipe"].stolen_cards) == 1

    def test_steal_prefers_uncommon(self):
        cs = fresh_with(ThievingHopper)
        prize = make_card("strike")
        prize.rarity = CardRarity.UNCOMMON  # shadow the class attr
        cs.player.discard_pile.append(prize)
        cs.hooks.register(prize)
        cs.end_turn()
        assert cs.enemy.powers["swipe"].stolen_cards == [prize]

    def test_full_route_ends_in_escape(self):
        cs = fresh_with(ThievingHopper)
        hopper = cs.enemy
        cs.end_turn()  # THIEVERY 17
        cs.end_turn()  # FLUTTER
        assert hopper.is_hovering
        assert hopper.powers["flutter"].amount == 5
        cs.player.hp = 80
        cs.end_turn()  # HAT_TRICK 21
        assert cs.player.hp == 80 - 21
        cs.player.hp = 80
        cs.end_turn()  # NAB 14
        assert cs.player.hp == 80 - 14
        cs.player.hp = 80
        cs.end_turn()  # ESCAPE
        assert hopper.escaped and not hopper.is_dead
        assert cs.is_over and cs.result.player_won

    def test_flutter_halves_damage_and_breaks_after_five_hits(self):
        cs = fresh_with(ThievingHopper)
        hopper = cs.enemy
        cs.end_turn()  # THIEVERY
        cs.end_turn()  # FLUTTER
        hp = hopper.hp
        strike = make_card("strike")
        DamageCmd.deal(cs.hooks, hopper, 10, dealer=cs.player, card=strike)
        assert hopper.hp == hp - 5  # halved
        assert hopper.powers["flutter"].amount == 4
        for _ in range(4):
            DamageCmd.deal(cs.hooks, hopper, 2, dealer=cs.player, card=strike)
        assert "flutter" not in hopper.powers
        assert hopper.stunned
        assert not hopper.is_hovering
        assert hopper.current_intent.move_type == MoveType.STUN
        hp = cs.player.hp
        cs.end_turn()  # stunned: HAT_TRICK is skipped
        assert cs.player.hp == hp
        cs.end_turn()  # then it resumes with the rolled move (NAB 14)
        assert cs.player.hp == hp - 14

    # ── Stolen-card return as a post-combat reward ───────────────────────
    # Source anchors (decompiled game, read-only):
    #   src/Core/Models/Powers/SwipePower.cs
    #     Steal():       CardPileCmd.RemoveFromDeck — the theft is permanent.
    #     BeforeDeath(): only when the owner dies; re-registers the card and
    #                    CombatRoom.AddExtraReward(SpecialCardReward). If the
    #                    hopper escapes instead, BeforeDeath never runs.
    #   src/Core/Rooms/CombatRoom.cs  AddExtraReward / ExtraRewards
    #   src/Core/Rewards/RewardsSet.cs WithRewardsFromRoom folds ExtraRewards
    #                    into the reward screen.
    #   src/Core/Rewards/SpecialCardReward.cs OnSelect adds it to the deck.

    @staticmethod
    def _hopper_run(seed: int = 3):
        from sts2_rl.run import RunState
        run = RunState(rng=random.Random(seed), max_hp=100000, hp=100000)
        enc = Encounter("thieving_hopper", [ThievingHopper])
        return run, enc

    def test_killing_hopper_returns_stolen_card_as_reward(self):
        from sts2_rl.rooms import RoomType
        from sts2_rl.cmds import CreatureCmd

        run, enc = self._hopper_run()
        combat = run.create_combat(enc, room_type=RoomType.MONSTER)
        combat.end_turn()  # THIEVERY: steal a card
        hopper = combat.enemy
        stolen_copy = hopper.powers["swipe"].stolen_cards[0]
        CreatureCmd.kill(combat.hooks, hopper)  # BeforeDeath fires
        deck_before = list(run.deck)
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        removed = [c for c in deck_before if c not in run.deck]
        assert len(removed) == 1               # the theft left the deck
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        # The reward is the deck version of the stolen card (the game queues
        # SpecialCardReward(StolenCard.DeckVersion)), take-or-skip.
        assert rewards.special_cards == removed
        assert removed[0].id == stolen_copy.id
        # Taking it (SpecialCardReward.OnSelect: CardPileCmd.Add to Deck)
        # restores the deck.
        run.add_card(rewards.special_cards[0])
        assert len(run.deck) == len(deck_before)
        # The channel drains: a second screen would not re-offer it.
        assert not run.pending_reward_extras

    def test_theft_removes_the_card_from_the_run_deck(self):
        from sts2_rl.rooms import RoomType

        run, enc = self._hopper_run()
        deck_before = len(run.deck)
        combat = run.create_combat(enc, room_type=RoomType.MONSTER)
        combat.end_turn()  # THIEVERY: steal
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        assert len(run.deck) == deck_before - 1

    def test_escaped_hopper_gives_no_reward_and_keeps_card_lost(self):
        from sts2_rl.rooms import RoomType

        run, enc = self._hopper_run()
        deck_before = len(run.deck)
        combat = run.create_combat(enc, room_type=RoomType.MONSTER)
        for _ in range(5):  # THIEVERY, FLUTTER, HAT_TRICK, NAB, ESCAPE
            combat.end_turn()
        assert combat.enemies[0].escaped
        run.finish_combat(combat, room_type=RoomType.MONSTER)
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        assert not rewards.special_cards          # BeforeDeath never fired
        assert len(run.deck) == deck_before - 1    # theft stays permanent


# ═════════════════════════════════════════════════════════════════════════
# Tunneler
# ═════════════════════════════════════════════════════════════════════════

class TestTunneler:
    def test_cycle_and_persistent_block(self):
        cs = fresh_with(Tunneler)
        tunneler = cs.enemy
        assert tunneler.max_hp == 87
        cs.end_turn()  # BITE 13
        assert cs.player.hp == 80 - 13
        cs.end_turn()  # BURROW: 32 block
        assert tunneler.block == 32
        assert "burrowed" in tunneler.powers
        cs.end_turn()  # BELOW 23 — burrow block survives its turn start
        assert cs.player.hp == 80 - 13 - 23
        assert tunneler.block == 32
        cs.end_turn()  # BELOW repeats
        assert cs.player.hp == 80 - 13 - 46

    def test_breaking_the_burrow_stuns(self):
        cs = fresh_with(Tunneler)
        tunneler = cs.enemy
        cs.end_turn()  # BITE
        cs.end_turn()  # BURROW
        DamageCmd.deal(cs.hooks, tunneler, 40, dealer=cs.player)  # breaks 32 block
        assert tunneler.hp == tunneler.max_hp - 8
        assert "burrowed" not in tunneler.powers
        assert tunneler.block == 0
        assert tunneler.current_intent.move_type == MoveType.STUN
        hp = cs.player.hp
        cs.end_turn()  # DIZZY: loses the turn
        assert cs.player.hp == hp
        cs.end_turn()  # starts over at BITE
        assert cs.player.hp == hp - 13

    def test_fully_absorbed_hit_does_not_break_it(self):
        cs = fresh_with(Tunneler)
        tunneler = cs.enemy
        cs.end_turn()
        cs.end_turn()  # burrowed with 32 block
        DamageCmd.deal(cs.hooks, tunneler, 30, dealer=cs.player)
        assert "burrowed" in tunneler.powers
        assert tunneler.block == 2


# ═════════════════════════════════════════════════════════════════════════
# Decimillipede
# ═════════════════════════════════════════════════════════════════════════

class TestDecimillipede:
    def test_three_segments_distinct_even_hp_staggered_moves(self):
        for seed in range(10):
            cs = fresh_encounter(DECIMILLIPEDE_ELITE, seed)
            assert len(cs.enemies) == 3
            hps = [e.max_hp for e in cs.enemies]
            assert len(set(hps)) == 3
            for hp in hps:
                assert hp % 2 == 0
                assert 40 <= hp <= 46
            assert {e._current_move.id for e in cs.enemies} == {
                "WRITHE_MOVE", "BULK_MOVE", "CONSTRICT_MOVE",
            }

    def test_first_turn_damage(self):
        cs = fresh_encounter(DECIMILLIPEDE_ELITE)
        cs.end_turn()  # writhe 5x2 + bulk 6 + constrict 8 (in some order)
        assert cs.player.hp == 80 - 10 - 6 - 8
        assert cs.player.powers["weak"].amount == 1

    def test_killed_segment_withers_and_reattaches(self):
        cs = fresh_encounter(DECIMILLIPEDE_ELITE)
        victim = cs.enemies[0]
        DamageCmd.deal(cs.hooks, victim, 999, dealer=cs.player)
        assert not cs.is_over
        reattach = victim.powers["reattach"]
        assert reattach.is_reviving
        assert victim._current_move.id == "DEAD_MOVE"
        assert victim.current_intent.move_type == MoveType.HIDDEN
        # Unhittable while withered.
        assert DamageCmd.deal(cs.hooks, victim, 10, dealer=cs.player) == 0
        cs.player.hp = 80
        cs.end_turn()  # DEAD_MOVE (nothing); now telegraphs the reattach
        assert victim.current_intent.move_type == MoveType.HEAL
        cs.player.hp = 80
        cs.end_turn()  # REATTACH: back with 25 HP
        assert not reattach.is_reviving
        assert victim.hp == 25

    def test_killing_last_standing_segment_ends_the_fight(self):
        cs = fresh_encounter(DECIMILLIPEDE_ELITE)
        a, b, c = cs.enemies
        DamageCmd.deal(cs.hooks, a, 999, dealer=cs.player)
        DamageCmd.deal(cs.hooks, b, 999, dealer=cs.player)
        assert not cs.is_over
        assert a.powers["reattach"].is_reviving
        assert b.powers["reattach"].is_reviving
        DamageCmd.deal(cs.hooks, c, 999, dealer=cs.player)
        assert a.is_dead and b.is_dead and c.is_dead
        # The win check runs at the call sites (play_card / enemy turns).
        assert cs._all_enemies_dead()


# ═════════════════════════════════════════════════════════════════════════
# Entomancer
# ═════════════════════════════════════════════════════════════════════════

class TestEntomancer:
    def test_cycle_and_pheromones(self):
        cs = fresh_with(Entomancer)
        ento = cs.enemy
        assert ento.max_hp == 145
        assert ento.powers["personal_hive"].amount == 1
        cs.end_turn()  # BEES 3x7
        assert cs.player.hp == 80 - 21
        cs.player.hp = 80
        cs.end_turn()  # SPEAR 18
        assert cs.player.hp == 80 - 18
        cs.player.hp = 80
        cs.end_turn()  # PHEROMONE_SPIT: hive < 3 -> +1 hive, +1 Str
        assert ento.powers["personal_hive"].amount == 2
        assert ento.strength == 1
        cs.player.hp = 80
        cs.end_turn()  # BEES (3+1)x7
        assert cs.player.hp == 80 - 28

    def test_hive_maxes_at_three_then_double_strength(self):
        cs = fresh_with(Entomancer)
        ento = cs.enemy
        ctx = cs._ctx()
        ento._spit(ctx)  # 1 -> 2, +1 Str
        ento._spit(ctx)  # 2 -> 3, +1 Str
        ento._spit(ctx)  # capped: +2 Str
        assert ento.powers["personal_hive"].amount == 3
        assert ento.strength == 4

    def test_hive_shuffles_dazed_per_hit_even_blocked(self):
        cs = fresh_with(Entomancer)
        ento = cs.enemy
        strike = make_card("strike")
        DamageCmd.deal(cs.hooks, ento, 6, dealer=cs.player, card=strike)
        assert sum(1 for c in cs.player.draw_pile if c.id == "dazed") == 1
        ento.block = 50
        DamageCmd.deal(cs.hooks, ento, 6, dealer=cs.player, card=strike)
        assert sum(1 for c in cs.player.draw_pile if c.id == "dazed") == 2


# ═════════════════════════════════════════════════════════════════════════
# Infested Prism
# ═════════════════════════════════════════════════════════════════════════

class TestInfestedPrism:
    def test_skills_start_tainted(self):
        cs = fresh_with(InfestedPrism)
        assert cs.enemy.max_hp == 161
        defends = [c for c in cs.player.all_cards if c.id == "defend"]
        assert defends
        for card in defends:
            assert isinstance(card.affliction, TaintedAffliction)
            assert card.affliction.amount == 2
        strikes = [c for c in cs.player.all_cards if c.id == "strike"]
        for card in strikes:
            assert card.affliction is None

    def test_playing_tainted_skill_raises_damage_taken(self):
        cs = fresh_with(InfestedPrism)
        defend = next(
            (c for c in cs.player.hand if c.id == "defend"), None
        )
        if defend is None:
            pytest.skip("no Defend in the opening hand for this seed")
        assert cs.play_card(cs.player.hand.index(defend))
        assert cs.player.powers["tainted"].amount == 2
        cs.player.block = 0
        cs.end_turn()  # JAB 15 + 2; Tainted removed at enemy side end
        assert cs.player.hp == 80 - 17
        assert "tainted" not in cs.player.powers

    def test_cycle_with_pulsate_stacking_spark(self):
        cs = fresh_with(InfestedPrism)
        prism = cs.enemy
        cs.end_turn()  # JAB 15
        assert cs.player.hp == 80 - 15
        cs.player.hp = 80
        cs.end_turn()  # RADIATE 11 + 11 block
        assert cs.player.hp == 80 - 11
        assert prism.block == 11
        cs.player.hp = 80
        cs.end_turn()  # WHIRLWIND 5x3
        assert cs.player.hp == 80 - 15
        cs.player.hp = 80
        cs.end_turn()  # PULSATE 8 + 20 block + Vital Spark +2
        assert cs.player.hp == 80 - 8
        assert prism.powers["vital_spark"].amount == 4
        defend = next(c for c in cs.player.all_cards if c.id == "defend")
        assert defend.affliction.amount == 4

    def test_afflictions_clear_when_prism_dies(self):
        cs = fresh_with(InfestedPrism)
        DamageCmd.deal(cs.hooks, cs.enemy, 999, dealer=cs.player)
        for card in cs.player.all_cards:
            assert not isinstance(card.affliction, TaintedAffliction)


# ═════════════════════════════════════════════════════════════════════════
# Kaiser Crab
# ═════════════════════════════════════════════════════════════════════════

class TestKaiserCrab:
    def test_composition_and_powers(self):
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        crusher, rocket = cs.enemies
        assert isinstance(crusher, Crusher) and isinstance(rocket, Rocket)
        assert crusher.max_hp == 209 and rocket.max_hp == 199
        assert "back_attack_left" in crusher.powers
        assert "back_attack_right" in rocket.powers
        assert "crab_rage" in crusher.powers and "crab_rage" in rocket.powers
        assert "surrounded" in cs.player.powers

    def test_back_attack_bonus_follows_facing(self):
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        # Facing right initially: the Crusher back-attacks for 12 * 1.5 = 18,
        # the Rocket's reticle hits for its plain 3.
        cs.end_turn()
        assert cs.player.hp == 80 - 18 - 3
        # Playing a targeted card at the Crusher turns the player around
        # (SurroundedPower.cs BeforeCardPlayed: cardPlay.Target != null).
        strike = make_card("strike")
        cs.player.hand.append(strike)
        assert cs.play_card(cs.player.hand.index(strike), target_idx=0)
        assert cs.player.powers["surrounded"].facing == "left"
        cs.player.hp = 80
        cs.end_turn()  # ENLARGING 4 plain + PRECISION 18 * 1.5 = 27
        assert cs.player.hp == 80 - 4 - 27

    def test_facing_flips_on_targeted_card_without_damage(self):
        """SurroundedPower.cs BeforeCardPlayed flips facing on ANY targeted
        card play (`cardPlay.Target != null`) — it is not conditioned on the
        card dealing damage. Tremble (a Skill that only applies Vulnerable)
        targeted at the Crusher must still turn the player around."""
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        crusher = cs.enemies[0]
        tremble = make_card("tremble")
        cs.player.hand.append(tremble)
        assert cs.player.powers["surrounded"].facing == "right"
        assert cs.play_card(cs.player.hand.index(tremble), target_idx=0)
        assert "vulnerable" in crusher.powers  # sanity: the card resolved
        assert cs.player.powers["surrounded"].facing == "left"

    def test_all_enemies_card_does_not_flip_facing(self):
        """An untargeted (TargetType.ALL_ENEMIES) card play has no
        `cardPlay.Target`, so it must not turn the player even though it
        damages both arms (mirrors SurroundedPower.cs BeforeCardPlayed)."""
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        dramatic_entrance = make_card("dramatic_entrance")
        cs.player.hand.append(dramatic_entrance)
        assert cs.play_card(cs.player.hand.index(dramatic_entrance))
        assert cs.player.powers["surrounded"].facing == "right"

    def test_crab_rage_on_partner_death(self):
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        crusher, rocket = cs.enemies
        DamageCmd.deal(cs.hooks, rocket, 999, dealer=cs.player)
        assert crusher.strength == 6
        assert crusher.block == 99
        assert "crab_rage" not in crusher.powers
        # With only the Crusher left the player faces it: no more back attacks.
        assert cs.player.powers["surrounded"].facing == "left"
        cs.player.hp = 80
        cs.end_turn()  # THRASH 12 + 6, un-multiplied
        assert cs.player.hp == 80 - 18

    def test_rocket_cycle(self):
        cs = fresh_encounter(KAISER_CRAB_BOSS)
        rocket = cs.enemies[1]
        moves = []
        for _ in range(6):
            moves.append(rocket._current_move.id)
            cs.player.hp = 80
            cs.end_turn()
        assert moves == [
            "TARGETING_RETICLE_MOVE", "PRECISION_BEAM_MOVE", "CHARGE_UP_MOVE",
            "LASER_MOVE", "RECHARGE_MOVE", "TARGETING_RETICLE_MOVE",
        ]


# ═════════════════════════════════════════════════════════════════════════
# Knowledge Demon
# ═════════════════════════════════════════════════════════════════════════

class TestKnowledgeDemon:
    def test_cycle(self):
        cs = fresh_with(KnowledgeDemon)
        kd = cs.enemy
        assert kd.max_hp == 379
        moves = []
        for _ in range(9):
            moves.append(kd._current_move.id)
            cs.player.hp = 80
            cs.player.powers.pop("disintegration", None)
            cs.end_turn()
        assert moves == [
            "CURSE_OF_KNOWLEDGE_MOVE", "SLAP_MOVE", "KNOWLEDGE_OVERWHELMING_MOVE",
            "PONDER_MOVE", "CURSE_OF_KNOWLEDGE_MOVE", "SLAP_MOVE",
            "KNOWLEDGE_OVERWHELMING_MOVE", "PONDER_MOVE",
            "CURSE_OF_KNOWLEDGE_MOVE",
        ]

    def test_choosing_disintegration_escalates(self):
        cs = fresh_with(KnowledgeDemon)
        cs.card_selector = lambda purpose, cands, count: [cands[0]]
        cs.end_turn()  # curse 1: Disintegration 6
        assert cs.player.powers["disintegration"].amount == 6
        cs.player.hp = 80
        hp = cs.player.hp
        cs.end_turn()  # turn end: take 6, then SLAP 17
        assert cs.player.hp == hp - 6 - 17
        for _ in range(3):  # OVERWHELM, PONDER, curse 2 (Disintegration 7)
            cs.player.hp = 80
            cs.end_turn()
        assert cs.player.powers["disintegration"].amount == 13

    def test_choosing_the_alternatives(self):
        cs = fresh_with(KnowledgeDemon)
        cs.card_selector = lambda purpose, cands, count: [cands[1]]
        cs.end_turn()  # curse 1: Mind Rot 1
        assert cs.player.powers["mind_rot"].amount == 1
        assert len(cs.player.hand) == 4  # drew one fewer
        for _ in range(4):  # SLAP, OVERWHELM, PONDER, curse 2: Sloth
            cs.player.hp = 80
            cs.end_turn()
        assert cs.player.powers["sloth"].amount == 3
        played = 0
        for _ in range(4):
            playable = [a for a in cs.valid_actions() if a != 0]
            if not playable:
                break
            assert cs.play_card(playable[0] - 1)
            played += 1
        assert played == 3  # Sloth caps at 3 plays
        for _ in range(4):  # SLAP, OVERWHELM, PONDER, curse 3: Waste Away
            cs.player.hp = 80
            cs.end_turn()
        assert cs.player.powers["waste_away"].amount == 1
        cs.player.hp = 80
        cs.end_turn()
        assert cs.player.energy == 2

    def test_ponder_heals_and_buffs(self):
        cs = fresh_with(KnowledgeDemon)
        kd = cs.enemy
        DamageCmd.deal(cs.hooks, kd, 50, dealer=cs.player)
        for _ in range(3):  # CURSE, SLAP, OVERWHELM
            cs.player.hp = 80
            cs.end_turn()
        hp = kd.hp
        cs.player.hp = 80
        cs.end_turn()  # PONDER: 11 + heal 30 + 2 Str
        assert kd.hp == hp + 30
        assert kd.strength == 2


# ═════════════════════════════════════════════════════════════════════════
# The Insatiable
# ═════════════════════════════════════════════════════════════════════════

class TestTheInsatiable:
    def test_liquify_sets_the_table(self):
        cs = fresh_encounter(THE_INSATIABLE_BOSS)
        boss = cs.enemy
        assert boss.max_hp == 321
        cs.end_turn()  # LIQUIFY_GROUND
        assert cs.player.hp == 80
        assert boss.powers["sandpit"].amount == 4
        escapes = [c for c in cs.player.all_cards if c.id == "frantic_escape"]
        assert len(escapes) == 6

    def test_devoured_when_the_timer_runs_out(self):
        cs = fresh_encounter(THE_INSATIABLE_BOSS)
        boss = cs.enemy
        cs.end_turn()  # LIQUIFY (Sandpit 4)
        for expected in (3, 2, 1):
            cs.player.hp = 80
            cs.end_turn()
            assert boss.powers["sandpit"].amount == expected
        cs.player.hp = 80
        cs.player.block = 999
        cs.end_turn()  # timer hits 0 at the boss's turn start: eaten alive
        assert cs.player.is_dead
        assert cs.is_over and not cs.result.player_won

    def test_frantic_escape_buys_a_turn(self):
        cs = fresh_encounter(THE_INSATIABLE_BOSS)
        boss = cs.enemy
        cs.end_turn()  # LIQUIFY
        from sts2_rl.cmds import CardPileCmd
        escape = make_card("frantic_escape")
        CardPileCmd.add_to_hand(cs.hooks, cs.player, escape)
        assert escape.energy_cost == 1
        assert cs.play_card(cs.player.hand.index(escape))
        assert boss.powers["sandpit"].amount == 5
        assert escape.energy_cost == 2  # costs 1 more for the rest of combat

    def test_attack_cycle(self):
        cs = fresh_encounter(THE_INSATIABLE_BOSS)
        boss = cs.enemy
        moves = []
        for _ in range(9):
            moves.append(boss._current_move.id)
            cs.player.hp = 80
            # keep the devour timer from ending the test fight
            if "sandpit" in boss.powers:
                boss.powers["sandpit"].amount = 9
            cs.end_turn()
        assert moves == [
            "LIQUIFY_GROUND_MOVE", "THRASH_MOVE", "LUNGING_BITE_MOVE",
            "SALIVATE_MOVE", "THRASH_MOVE_2", "THRASH_MOVE",
            "LUNGING_BITE_MOVE", "SALIVATE_MOVE", "THRASH_MOVE_2",
        ]


# ═════════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════════

class TestRegistry:
    def test_all_encounters_playable(self):
        for key, enc in ENCOUNTERS.items():
            cs = CombatState(rng=random.Random(1), encounter=enc)
            turns = 0
            while not cs.is_over and turns < 60:
                cs.end_turn()
                turns += 1
            assert cs.is_over, f"{key} never ended"

    def test_expected_keys(self):
        assert set(ENCOUNTERS) == {
            "bowlbugs_weak", "exoskeletons_weak", "thieving_hopper", "tunneler",
            "bowlbugs_normal", "chompers", "exoskeletons_normal",
            "hunter_killer", "louse_progenitor", "mytes", "ovicopter",
            "slumbering_beetle", "spiny_toad", "the_obscura",
            "decimillipede", "entomancer", "infested_prisms",
            "kaiser_crab", "knowledge_demon", "the_insatiable",
        }
