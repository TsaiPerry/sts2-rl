"""
Tests for the Underdocks (Act 2) enemies and their powers (Ravenous, Suck,
Surprise, Smoggy, Skittish, Asleep, Vigor, Shriek, Hardened Shell,
Steam Eruption).

Run with:  py -m pytest test/test_underdocks.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import CardType, DazedCard, make_card
from sts2_rl.monsters import Encounter, MoveType
from sts2_rl.monsters.underdocks import (
    CalcifiedCultist,
    CorpseSlug,
    DampCultist,
    FatGremlin,
    FossilStalker,
    GasBomb,
    GremlinMerc,
    HauntedShip,
    LagavulinMatriarch,
    LivingFog,
    PhantasmalGardener,
    PunchConstruct,
    Seapunk,
    SewerClam,
    SkulkingColony,
    SludgeSpinner,
    SneakyGremlin,
    SoulFysh,
    TerrorEel,
    Toadpole,
    TwoTailedRat,
    WaterfallGiant,
    CORPSE_SLUGS_NORMAL,
    CORPSE_SLUGS_WEAK,
    CULTISTS_NORMAL,
    ENCOUNTERS,
    GREMLIN_MERC_NORMAL,
    LAGAVULIN_MATRIARCH_BOSS,
    PHANTASMAL_GARDENERS_ELITE,
    SEAPUNK_NORMAL,
    SOUL_FYSH_BOSS,
    TOADPOLES_WEAK,
    TWO_TAILED_RATS_NORMAL,
    WATERFALL_GIANT_BOSS,
)
from sts2_rl.afflictions import SmogAffliction
from sts2_rl.powers import SmoggyPower


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


def fresh_encounter(enc: Encounter, seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed), encounter=enc)


# ═════════════════════════════════════════════════════════════════════════
# Corpse Slugs
# ═════════════════════════════════════════════════════════════════════════

class TestCorpseSlug:
    def test_hp_range(self):
        for seed in range(10):
            slug = fresh_with(CorpseSlug, seed).enemy
            assert 25 <= slug.max_hp <= 27

    def test_move_cycle(self):
        cs = fresh_with(CorpseSlug)
        slug = cs.enemy
        seen = []
        for _ in range(6):
            seen.append(slug._current_move.id)
            cs.end_turn()
        assert seen == [
            "WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE",
            "WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE",
        ]

    def test_goop_applies_frail(self):
        cs = fresh_with(CorpseSlug)
        cs.end_turn()  # whip slap 3x2
        cs.end_turn()  # glomp 8
        assert cs.player.hp == 80 - 6 - 8
        cs.end_turn()  # goop: Frail 2 (first side-end tick skipped)
        assert cs.player.powers["frail"].amount == 2

    def test_encounter_staggers_starting_moves(self):
        for seed in range(5):
            cs = fresh_encounter(CORPSE_SLUGS_NORMAL, seed)
            starts = {e._current_move.id for e in cs.enemies}
            assert starts == {"WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE"}

    def test_weak_encounter_has_two_slugs(self):
        cs = fresh_encounter(CORPSE_SLUGS_WEAK)
        assert len(cs.enemies) == 2
        assert len({e._current_move.id for e in cs.enemies}) == 2

    def test_ravenous_devours_fallen_slug(self):
        cs = fresh_encounter(CORPSE_SLUGS_NORMAL)
        victim, other = cs.enemies[0], cs.enemies[1]
        DamageCmd.deal(cs.hooks, victim, 99, dealer=cs.player)
        assert victim.is_dead
        # The survivors devour the corpse: stunned + 4 Strength each.
        for slug in cs.enemies[1:]:
            assert slug.stunned
            assert slug.strength == 4
            assert slug.current_intent.move_type == MoveType.STUN
        # The stunned turn deals no damage.
        hp = cs.player.hp
        cs.end_turn()
        assert cs.player.hp == hp

    def test_ravenous_does_not_trigger_on_own_death(self):
        cs = fresh_encounter(CORPSE_SLUGS_WEAK)
        victim = cs.enemies[0]
        DamageCmd.deal(cs.hooks, victim, 99, dealer=cs.player)
        assert not victim.stunned
        assert victim.powers.get("strength") is None


# ═════════════════════════════════════════════════════════════════════════
# Cultists
# ═════════════════════════════════════════════════════════════════════════

class TestCultists:
    def test_encounter_composition(self):
        cs = fresh_encounter(CULTISTS_NORMAL)
        assert isinstance(cs.enemies[0], CalcifiedCultist)
        assert isinstance(cs.enemies[1], DampCultist)
        assert 38 <= cs.enemies[0].max_hp <= 41
        assert 51 <= cs.enemies[1].max_hp <= 53

    def test_incantation_then_scaling_strikes(self):
        # MOVED 2026-07-29 (round 7, power/ritual/AfterApplied). It used to
        # assert strength 2 / 5 after the FIRST turn end and 4 / 10 after the
        # second. RitualPower.cs:36-43 sets WasJustAppliedByEnemy from
        # `base.Owner.IsEnemy` alone, so a monster that buffs ITSELF skips its
        # first AfterSideTurnEnd -- and every ported Ritual source is exactly
        # that. The whole ladder therefore shifts one turn later, and the
        # turn-2 strikes land unbuffed.
        cs = fresh_encounter(CULTISTS_NORMAL)
        calc, damp = cs.enemies
        cs.end_turn()  # both cast INCANTATION; the first Ritual is SKIPPED
        assert cs.player.hp == 80
        assert calc.strength == 0 and damp.strength == 0
        cs.end_turn()  # dark strikes at base: 9 + 1, then Ritual fires
        assert cs.player.hp == 80 - 9 - 1
        assert calc.strength == 2 and damp.strength == 5
        cs.end_turn()  # now buffed: (9+2) + (1+5), then Ritual again
        assert cs.player.hp == 80 - 9 - 1 - 11 - 6
        assert calc.strength == 4 and damp.strength == 10


# ═════════════════════════════════════════════════════════════════════════
# Fossil Stalker
# ═════════════════════════════════════════════════════════════════════════

class TestFossilStalker:
    def test_starts_with_latch(self):
        cs = fresh_with(FossilStalker)
        stalker = cs.enemy
        assert stalker._current_move.id == "LATCH_MOVE"
        assert "suck" in stalker.powers

    def test_suck_gains_strength_on_unblocked_hit(self):
        cs = fresh_with(FossilStalker)
        stalker = cs.enemy
        cs.end_turn()  # LATCH: 12 unblocked → Suck grants 3 Strength
        assert cs.player.hp == 80 - 12
        assert stalker.strength == 3

    def test_suck_ignores_fully_blocked_hit(self):
        cs = fresh_with(FossilStalker)
        stalker = cs.enemy
        cs.player.block = 50
        cs.end_turn()
        assert stalker.powers.get("strength") is None

    def test_never_three_in_a_row(self):
        for seed in range(20):
            cs = fresh_with(FossilStalker, seed)
            stalker = cs.enemy
            moves = []
            for _ in range(12):
                moves.append(stalker._current_move.id)
                cs.player.hp = 80  # stay alive
                cs.player.block = 99  # keep Suck from snowballing
                cs.end_turn()
                if cs.is_over:
                    break
            for i in range(len(moves) - 2):
                assert not (moves[i] == moves[i + 1] == moves[i + 2])


# ═════════════════════════════════════════════════════════════════════════
# Gremlin Merc
# ═════════════════════════════════════════════════════════════════════════

class TestGremlinMerc:
    def test_move_cycle_and_debuffs(self):
        cs = fresh_encounter(GREMLIN_MERC_NORMAL)
        merc = cs.enemy
        assert merc._current_move.id == "GIMME_MOVE"
        cs.end_turn()  # GIMME 7x2
        assert cs.player.hp == 80 - 14
        cs.end_turn()  # DOUBLE_SMASH 6x2 + Weak 2 (weakens the player, not the merc)
        assert cs.player.hp == 80 - 14 - 12
        assert cs.player.powers["weak"].amount == 2  # first tick skipped
        cs.end_turn()  # HEHE 8 + self Str 2
        assert cs.player.hp == 80 - 14 - 12 - 8
        assert merc.strength == 2

    def test_surprise_spawns_gremlins_on_death(self):
        cs = fresh_encounter(GREMLIN_MERC_NORMAL)
        merc = cs.enemy
        DamageCmd.deal(cs.hooks, merc, 99, dealer=cs.player)
        assert merc.is_dead
        assert not cs.is_over
        types = [type(e) for e in cs.enemies]
        assert types == [GremlinMerc, SneakyGremlin, FatGremlin]
        sneaky, fat = cs.enemies[1], cs.enemies[2]
        assert sneaky.current_intent.move_type == MoveType.STUN
        assert fat.current_intent.move_type == MoveType.STUN

        hp = cs.player.hp
        cs.end_turn()  # both gremlins wake up (no-op)
        assert cs.player.hp == hp
        assert fat.current_intent.move_type == MoveType.ESCAPE
        cs.end_turn()  # sneaky tackles 9, fat flees
        assert cs.player.hp == hp - 9
        assert fat.escaped and not fat.is_dead
        # Killing the sneaky gremlin now wins the fight.
        DamageCmd.deal(cs.hooks, sneaky, 99, dealer=cs.player)
        assert cs._all_enemies_dead()


# ═════════════════════════════════════════════════════════════════════════
# Haunted Ship
# ═════════════════════════════════════════════════════════════════════════

class TestHauntedShip:
    def test_haunt_then_swipe_stomp_loop(self):
        cs = fresh_with(HauntedShip)
        ship = cs.enemy
        assert ship.max_hp == 63
        intent = ship.current_intent
        assert intent.move_type == MoveType.DEBUFF
        assert intent.has(MoveType.STATUS_CARD)

        cs.end_turn()  # HAUNT: Weak 3 + 5 Dazed
        assert cs.player.hp == 80
        # A player debuff skips its first side-end tick (SkipNextDurationTick).
        assert cs.player.powers["weak"].amount == 3
        dazed = [c for c in cs.player.all_cards if isinstance(c, DazedCard)]
        assert len(dazed) == 5

        assert ship._current_move.id == "SWIPE_MOVE"
        hp = cs.player.hp
        cs.end_turn()  # SWIPE 13
        assert cs.player.hp == hp - 13
        assert ship._current_move.id == "STOMP_MOVE"
        hp = cs.player.hp
        cs.end_turn()  # STOMP 4x3
        assert cs.player.hp == hp - 12
        assert ship._current_move.id == "SWIPE_MOVE"


# ═════════════════════════════════════════════════════════════════════════
# Living Fog + Gas Bombs
# ═════════════════════════════════════════════════════════════════════════

class TestLivingFog:
    def test_opening_gas_applies_smoggy(self):
        cs = fresh_with(LivingFog)
        cs.end_turn()  # ADVANCED_GAS 8 + Smoggy
        assert cs.player.hp == 80 - 8
        assert "smoggy" in cs.player.powers

    def test_bloat_spawns_bomb_that_explodes(self):
        cs = fresh_with(LivingFog)
        cs.end_turn()  # ADVANCED_GAS 8
        cs.end_turn()  # BLOAT: spawn bomb + 5
        assert cs.player.hp == 80 - 8 - 5
        assert len(cs.enemies) == 2
        bomb = cs.enemies[0]  # bomb1 sorts ahead of the fog's livingFog slot
        assert isinstance(bomb, GasBomb)
        assert "minion" in bomb.powers
        assert bomb.current_intent.move_type == MoveType.DEATH_BLOW
        cs.end_turn()  # SUPER_GAS_BLAST 8, bomb explodes for 8 and dies
        assert cs.player.hp == 80 - 8 - 5 - 8 - 8
        assert bomb.is_dead

    def test_bomb_spawns_into_its_slot_ahead_of_the_fog(self):
        """LivingFogNormal.Slots = [bomb1..bomb5, livingFog], BloatMove takes
        Encounter.GetNextSlot (the FIRST unoccupied slot -> bomb1) and
        CombatManager.AddCreature re-sorts Enemies by Slots.IndexOf whenever
        the added creature carries a slot (SortEnemiesBySlotName). A spawned
        Gas Bomb therefore lands BEFORE the Living Fog (slot index 5), and
        successive bombs fill bomb2, bomb3... behind it -- the spawn is not
        appended at the end of the enemy list."""
        cs = fresh_with(LivingFog)
        fog = cs.enemies[0]
        fog._bloat(cs._ctx())
        assert [type(e).__name__ for e in cs.enemies] == ["GasBomb", "LivingFog"]
        first = cs.enemies[0]
        cs.player.hp = 80
        fog._bloat(cs._ctx())
        assert [type(e).__name__ for e in cs.enemies] == [
            "GasBomb", "GasBomb", "LivingFog"]
        assert cs.enemies[0] is first  # bomb1 keeps its slot; the new one is bomb2

    def test_a_freed_bomb_slot_is_refilled_from_the_front(self):
        """GetNextSlot is FirstOrDefault(unoccupied), so once the bomb1
        occupant dies the next spawn reclaims bomb1 and sorts ahead of the
        bomb2 occupant."""
        cs = fresh_with(LivingFog)
        fog = cs.enemies[0]
        fog._bloat(cs._ctx())
        cs.player.hp = 80
        fog._bloat(cs._ctx())
        cs.player.hp = 80
        bomb1, bomb2 = cs.enemies[0], cs.enemies[1]
        DamageCmd.deal(cs.hooks, bomb1, 999, dealer=cs.player)
        fog._bloat(cs._ctx())
        live = [e for e in cs.enemies if isinstance(e, GasBomb) and not e.is_gone]
        assert live[1] is bomb2
        assert cs.enemies.index(live[0]) < cs.enemies.index(bomb2)

    def test_bomb_count_capped_at_five_slots(self):
        cs = fresh_with(LivingFog)
        fog = cs.enemies[0]
        for _ in range(6):
            fog._bloat(cs._ctx())
            cs.player.hp = 80
        bombs = [e for e in cs.enemies if isinstance(e, GasBomb)]
        assert len(bombs) == 5

    def test_minion_bombs_do_not_prolong_combat(self):
        cs = fresh_with(LivingFog)
        fog = cs.enemies[0]
        fog._bloat(cs._ctx())
        DamageCmd.deal(cs.hooks, fog, 999, dealer=cs.player)
        assert cs._all_enemies_dead()

    def test_smoggy_locks_other_skills_for_the_turn(self):
        cs = fresh_with(LivingFog)
        PowerCmd.apply(cs.hooks, cs.player, SmoggyPower, 1)
        skills = [c for c in cs.player.hand if c.card_type == CardType.SKILL]
        if len(skills) < 2:
            pytest.skip("need two skills in the opening hand for this seed")
        first = cs.player.hand.index(skills[0])
        assert cs.play_card(first)
        # Every other Skill the player owns is now smogged and unplayable.
        for c in cs.player.hand:
            if c.card_type == CardType.SKILL:
                assert isinstance(c.affliction, SmogAffliction)
                assert not cs.hooks.should_play_card(c)
            else:
                assert cs.hooks.should_play_card(c)
        # Smog clears at the end of the player's turn.
        cs.end_turn()
        assert all(
            not isinstance(c.affliction, SmogAffliction)
            for c in cs.player.all_cards
        )
        # And skills are playable again next turn.
        for c in cs.player.hand:
            assert cs.hooks.should_play_card(c)


# ═════════════════════════════════════════════════════════════════════════
# Phantasmal Gardeners
# ═════════════════════════════════════════════════════════════════════════

class TestPhantasmalGardeners:
    def test_four_gardeners_start_offset_in_cycle(self):
        cs = fresh_encounter(PHANTASMAL_GARDENERS_ELITE)
        assert len(cs.enemies) == 4
        starts = [e._current_move.id for e in cs.enemies]
        assert starts == ["FLAIL_MOVE", "BITE_MOVE", "LASH_MOVE", "ENLARGE_MOVE"]

    def test_first_turn_damage_and_enlarge(self):
        cs = fresh_encounter(PHANTASMAL_GARDENERS_ELITE)
        fourth = cs.enemies[3]
        cs.end_turn()  # flail 1x3 + bite 5 + lash 7; fourth enlarges
        assert cs.player.hp == 80 - 3 - 5 - 7
        assert fourth.strength == 2

    def test_skittish_blocks_once_per_turn(self):
        cs = fresh_encounter(PHANTASMAL_GARDENERS_ELITE)
        gardener = cs.enemies[0]
        strike = make_card("strike")
        DamageCmd.deal(cs.hooks, gardener, 3, dealer=cs.player, card=strike)
        assert gardener.block == 6
        # Only the first unblocked card hit each turn triggers it: the second
        # hit chews through the 6 block without granting more.
        DamageCmd.deal(cs.hooks, gardener, 8, dealer=cs.player, card=strike)
        assert gardener.block == 0
        assert gardener.hp == gardener.max_hp - 3 - 2

    def test_skittish_ignores_fully_blocked_hits(self):
        cs = fresh_encounter(PHANTASMAL_GARDENERS_ELITE)
        gardener = cs.enemies[0]
        gardener.block = 10
        strike = make_card("strike")
        DamageCmd.deal(cs.hooks, gardener, 3, dealer=cs.player, card=strike)
        assert gardener.block == 7  # absorbed; no Skittish block

    def test_skittish_resets_next_turn(self):
        cs = fresh_encounter(PHANTASMAL_GARDENERS_ELITE)
        gardener = cs.enemies[0]
        strike = make_card("strike")
        DamageCmd.deal(cs.hooks, gardener, 3, dealer=cs.player, card=strike)
        assert gardener.block == 6
        cs.end_turn()
        DamageCmd.deal(cs.hooks, gardener, 3, dealer=cs.player, card=strike)
        assert gardener.block == 6  # cleared at its turn start, re-triggered


# ═════════════════════════════════════════════════════════════════════════
# Punch Construct
# ═════════════════════════════════════════════════════════════════════════

class TestPunchConstruct:
    def test_cycle_and_artifact(self):
        cs = fresh_with(PunchConstruct)
        construct = cs.enemy
        assert construct.max_hp == 55
        assert "artifact" in construct.powers

        cs.end_turn()  # READY: 10 block
        assert construct.block == 10
        cs.end_turn()  # FAST_PUNCH 5x2 + Frail 1 (survives its first side-end tick)
        assert cs.player.hp == 80 - 10
        assert "frail" in cs.player.powers
        cs.end_turn()  # STRONG_PUNCH 14
        assert cs.player.hp == 80 - 10 - 14
        assert construct._current_move.id == "READY_MOVE"

    def test_punch_off_reduction_cuts_current_hp_not_max(self):
        # PunchConstruct.cs:75-78 AfterAddedToRoom is
        # SetCurrentHpInternal(Max(1, CurrentHp - StartingHpReduction)) with
        # MaxHp fixed at 55 — the constructs come in damaged, not smaller.
        from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
        cs = fresh_encounter(PUNCH_OFF_EVENT_ENCOUNTER, seed=4)
        left, right = cs.enemies
        assert left.max_hp == 55 and right.max_hp == 55
        assert left.hp == 53 and right.hp == 49
        assert left._current_move.id == "FAST_PUNCH_MOVE"

    def test_artifact_blocks_first_player_debuff(self):
        cs = fresh_with(PunchConstruct)
        construct = cs.enemy
        from sts2_rl.powers import VulnerablePower
        PowerCmd.apply(cs.hooks, construct, VulnerablePower, 2)
        assert "vulnerable" not in construct.powers
        assert "artifact" not in construct.powers  # consumed
        PowerCmd.apply(cs.hooks, construct, VulnerablePower, 2)
        assert "vulnerable" in construct.powers


# ═════════════════════════════════════════════════════════════════════════
# Lagavulin Matriarch
# ═════════════════════════════════════════════════════════════════════════

class TestLagavulinMatriarch:
    def test_starts_asleep_with_plating(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        assert boss.max_hp == 222
        assert boss.powers["plating"].amount == 12
        assert boss.powers["asleep"].amount == 3
        assert boss.current_intent.move_type == MoveType.SLEEP

    def test_natural_wake_after_three_turns(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        cs.end_turn()  # sleep turn 1: plating gains 12 block
        assert cs.player.hp == 80
        assert boss.block == 12
        cs.end_turn()  # sleep turn 2 (plating decayed to 11)
        assert cs.player.hp == 80
        assert boss.block == 11
        cs.end_turn()  # sleep turn 3: plating removed early, then she wakes
        assert cs.player.hp == 80
        assert boss.block == 0
        assert "asleep" not in boss.powers
        assert "plating" not in boss.powers
        assert boss.is_awake
        intent = boss.current_intent
        assert intent.move_type == MoveType.ATTACK and intent.damage == 19
        cs.end_turn()  # SLASH
        assert cs.player.hp == 80 - 19

    def test_starts_with_platings_block(self):
        # Enemies that start with Plating start with its block (round 1).
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        assert cs.enemy.block == 12

    def test_unblocked_damage_wakes_her_early(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        # 18 chews through the starting Plating block (12) and lands 6.
        DamageCmd.deal(cs.hooks, boss, 18, dealer=cs.player)
        assert boss.is_awake
        assert "asleep" not in boss.powers
        assert "plating" not in boss.powers
        assert boss.stunned
        assert boss.current_intent.move_type == MoveType.STUN
        hp = cs.player.hp
        cs.end_turn()  # she spends the turn waking up
        assert cs.player.hp == hp
        assert boss.current_intent.damage == 19
        cs.end_turn()  # SLASH 19
        assert cs.player.hp == hp - 19

    def test_awake_move_cycle(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        DamageCmd.deal(cs.hooks, boss, 18, dealer=cs.player)
        cs.end_turn()  # wake-up turn
        moves = []
        for _ in range(8):
            moves.append(boss._current_move.id)
            cs.player.hp = 80  # stay alive through the loop
            cs.end_turn()
        assert moves == [
            "SLASH_MOVE", "DISEMBOWEL_MOVE", "SLASH2_MOVE", "SOUL_SIPHON_MOVE",
            "SLASH_MOVE", "DISEMBOWEL_MOVE", "SLASH2_MOVE", "SOUL_SIPHON_MOVE",
        ]

    def test_slash2_blocks_and_siphon_drains(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        DamageCmd.deal(cs.hooks, boss, 18, dealer=cs.player)
        cs.end_turn()  # wake-up
        cs.end_turn()  # SLASH 19
        cs.end_turn()  # DISEMBOWEL 9x2
        hp = cs.player.hp
        cs.end_turn()  # SLASH2: 12 + 12 block
        assert cs.player.hp == hp - 12
        assert boss.block == 12
        cs.end_turn()  # SOUL_SIPHON
        assert cs.player.powers["strength"].amount == -2
        assert cs.player.powers["dexterity"].amount == -2
        assert boss.strength == 2

    def test_fully_blocked_damage_does_not_wake_her(self):
        cs = fresh_encounter(LAGAVULIN_MATRIARCH_BOSS)
        boss = cs.enemy
        boss.block = 20
        DamageCmd.deal(cs.hooks, boss, 6, dealer=cs.player)
        assert not boss.is_awake
        assert "asleep" in boss.powers


# ═════════════════════════════════════════════════════════════════════════
# Seapunk
# ═════════════════════════════════════════════════════════════════════════

class TestSeapunk:
    def test_hp_range(self):
        for seed in range(10):
            punk = fresh_with(Seapunk, seed).enemy
            assert 44 <= punk.max_hp <= 46

    def test_move_cycle_and_bubble_burp(self):
        cs = fresh_with(Seapunk)
        punk = cs.enemy
        cs.end_turn()  # SEA_KICK 11
        assert cs.player.hp == 80 - 11
        cs.end_turn()  # SPINNING_KICK 2x4
        assert cs.player.hp == 80 - 11 - 8
        cs.end_turn()  # BUBBLE_BURP: 7 block + 1 Str
        assert punk.block == 7
        assert punk.strength == 1
        cs.end_turn()  # SEA_KICK 11 + 1
        assert cs.player.hp == 80 - 11 - 8 - 12

    def test_normal_encounter_adds_calcified_cultist(self):
        cs = fresh_encounter(SEAPUNK_NORMAL)
        assert isinstance(cs.enemies[0], CalcifiedCultist)
        assert isinstance(cs.enemies[1], Seapunk)


# ═════════════════════════════════════════════════════════════════════════
# Sewer Clam
# ═════════════════════════════════════════════════════════════════════════

class TestSewerClam:
    def test_starts_with_plating_and_its_block(self):
        cs = fresh_with(SewerClam)
        clam = cs.enemy
        assert clam.max_hp == 56
        assert clam.powers["plating"].amount == 8
        assert clam.block == 8

    def test_jet_then_pressurize_loop(self):
        cs = fresh_with(SewerClam)
        clam = cs.enemy
        cs.end_turn()  # JET 10 (plating: no decay on round 1, block 8 at end)
        assert cs.player.hp == 70
        assert clam.block == 8
        cs.end_turn()  # PRESSURIZE: +4 Str (plating decays to 7)
        assert clam.strength == 4
        assert clam.block == 7
        cs.end_turn()  # JET 10 + 4
        assert cs.player.hp == 70 - 14


# ═════════════════════════════════════════════════════════════════════════
# Skulking Colony
# ═════════════════════════════════════════════════════════════════════════

class TestSkulkingColony:
    def test_move_cycle(self):
        cs = fresh_with(SkulkingColony)
        colony = cs.enemy
        assert colony.max_hp == 75
        assert colony.powers["hardened_shell"].amount == 20
        cs.end_turn()  # ZOOM 14
        assert cs.player.hp == 66
        cs.end_turn()  # ZOOM 14
        assert cs.player.hp == 52
        cs.end_turn()  # INERTIA 9 + 2 Str
        assert cs.player.hp == 43
        assert colony.strength == 2
        cs.end_turn()  # PIERCING_STABS (7+2)x2
        assert cs.player.hp == 43 - 18

    def test_hardened_shell_caps_hp_loss_per_turn(self):
        cs = fresh_with(SkulkingColony)
        colony = cs.enemy
        DamageCmd.deal(cs.hooks, colony, 30, dealer=cs.player)
        assert colony.hp == 75 - 20  # capped
        DamageCmd.deal(cs.hooks, colony, 10, dealer=cs.player)
        assert colony.hp == 75 - 20  # cap already spent this turn
        cs.end_turn()
        DamageCmd.deal(cs.hooks, colony, 25, dealer=cs.player)
        assert colony.hp == 75 - 20 - 20  # cap reset for the new turn


# ═════════════════════════════════════════════════════════════════════════
# Sludge Spinner
# ═════════════════════════════════════════════════════════════════════════

class TestSludgeSpinner:
    def test_opens_with_oil_spray(self):
        cs = fresh_with(SludgeSpinner)
        spinner = cs.enemy
        assert 37 <= spinner.max_hp <= 39
        assert spinner._current_move.id == "OIL_SPRAY_MOVE"
        cs.end_turn()
        assert cs.player.hp == 72
        assert cs.player.powers["weak"].amount == 1  # first tick skipped

    def test_never_repeats_a_move(self):
        for seed in range(5):
            cs = fresh_with(SludgeSpinner, seed)
            spinner = cs.enemy
            moves = []
            for _ in range(10):
                moves.append(spinner._current_move.id)
                cs.player.hp = 80
                cs.end_turn()
            for a, b in zip(moves, moves[1:]):
                assert a != b


# ═════════════════════════════════════════════════════════════════════════
# Toadpoles
# ═════════════════════════════════════════════════════════════════════════

class TestToadpoles:
    def test_front_and_back_start_offset(self):
        cs = fresh_encounter(TOADPOLES_WEAK)
        front, back = cs.enemies
        assert front.is_front and not back.is_front
        assert front._current_move.id == "SPIKEN_MOVE"
        assert back._current_move.id == "WHIRL_MOVE"

    def test_spiken_then_spit_spends_the_thorns(self):
        cs = fresh_encounter(TOADPOLES_WEAK)
        front, back = cs.enemies
        cs.end_turn()  # front SPIKEN +2 Thorns; back WHIRL 7
        assert cs.player.hp == 73
        assert front.powers["thorns"].amount == 2
        cs.end_turn()  # front SPIKE_SPIT (Thorns spent, 3x3); back SPIKEN
        assert cs.player.hp == 73 - 9
        assert "thorns" not in front.powers  # stacked to 0 -> removed
        assert back.powers["thorns"].amount == 2
        cs.end_turn()  # front WHIRL 7; back SPIKE_SPIT 3x3
        assert cs.player.hp == 73 - 9 - 7 - 9
        assert "thorns" not in back.powers

    def test_thorns_reflect_while_spiked(self):
        cs = fresh_encounter(TOADPOLES_WEAK)
        front = cs.enemies[0]
        cs.end_turn()  # front now holds 2 Thorns
        hp = cs.player.hp
        DamageCmd.deal(cs.hooks, front, 1, dealer=cs.player)
        assert cs.player.hp == hp - 2


# ═════════════════════════════════════════════════════════════════════════
# Two-Tailed Rats
# ═════════════════════════════════════════════════════════════════════════

class TestTwoTailedRats:
    def test_three_rats_staggered_starts(self):
        cs = fresh_encounter(TWO_TAILED_RATS_NORMAL)
        assert len(cs.enemies) == 3
        for rat in cs.enemies:
            assert 17 <= rat.max_hp <= 21
        assert {r._current_move.id for r in cs.enemies} == {
            "SCRATCH_MOVE", "DISEASE_BITE_MOVE", "SCREECH_MOVE",
        }

    def test_first_turn_damage_and_frail(self):
        cs = fresh_encounter(TWO_TAILED_RATS_NORMAL)
        cs.end_turn()  # scratch 8 + bite 6 + screech (Frail 1)
        assert cs.player.hp == 80 - 8 - 6
        assert cs.player.powers["frail"].amount == 1  # first tick skipped

    def test_call_for_backup_limits(self):
        summoned_somewhere = False
        for seed in range(8):
            cs = fresh_encounter(TWO_TAILED_RATS_NORMAL, seed)
            for _ in range(30):
                cs.player.hp = 80
                cs.end_turn()
            assert len(cs.enemies) <= 5  # 5 slots
            counts = {r.call_for_backup_count for r in cs.enemies}
            assert len(counts) == 1  # count is synced across the pack
            assert counts.pop() <= 3
            if len(cs.enemies) > 3:
                summoned_somewhere = True
        assert summoned_somewhere


# ═════════════════════════════════════════════════════════════════════════
# Terror Eel
# ═════════════════════════════════════════════════════════════════════════

class TestTerrorEel:
    def test_crash_thrash_alternation_with_vigor(self):
        cs = fresh_with(TerrorEel)
        eel = cs.enemy
        assert eel.max_hp == 140
        assert eel.powers["shriek"].amount == 70
        cs.end_turn()  # CRASH 16
        assert cs.player.hp == 64
        cs.end_turn()  # THRASH 3x3, then +6 Vigor
        assert cs.player.hp == 55
        assert eel.powers["vigor"].amount == 6
        cs.end_turn()  # CRASH 16 + 6 (Vigor consumed by the attack)
        assert cs.player.hp == 55 - 22
        assert "vigor" not in eel.powers
        cs.end_turn()  # THRASH back to 3x3
        assert cs.player.hp == 55 - 22 - 9

    def test_shriek_triggers_terror(self):
        cs = fresh_with(TerrorEel)
        eel = cs.enemy
        DamageCmd.deal(cs.hooks, eel, 75, dealer=cs.player)  # 140 -> 65 <= 70
        assert eel.stunned
        assert "shriek" not in eel.powers
        assert eel.current_intent.move_type == MoveType.STUN
        cs.end_turn()  # stunned: no attack
        assert cs.player.hp == 80
        assert eel._current_move.id == "TERROR_MOVE"
        cs.end_turn()  # TERROR: Vulnerable 99
        assert cs.player.hp == 80
        assert cs.player.powers["vulnerable"].amount == 99
        assert eel._current_move.id == "CRASH_MOVE"
        cs.end_turn()  # CRASH into 99 Vulnerable: 16 * 1.5
        assert cs.player.hp == 80 - 24

    def test_shriek_needs_hp_at_or_below_threshold(self):
        cs = fresh_with(TerrorEel)
        eel = cs.enemy
        DamageCmd.deal(cs.hooks, eel, 60, dealer=cs.player)  # 140 -> 80 > 70
        assert not eel.stunned
        assert "shriek" in eel.powers

    def test_fully_blocked_hit_does_not_trigger_shriek(self):
        cs = fresh_with(TerrorEel)
        eel = cs.enemy
        eel.hp = 71
        eel.block = 100
        DamageCmd.deal(cs.hooks, eel, 75, dealer=cs.player)
        assert not eel.stunned
        assert "shriek" in eel.powers


# ═════════════════════════════════════════════════════════════════════════
# Soul Fysh
# ═════════════════════════════════════════════════════════════════════════

class TestSoulFysh:
    def test_move_cycle(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        fysh = cs.enemy
        assert fysh.max_hp == 211
        moves = []
        for _ in range(6):
            moves.append(fysh._current_move.id)
            cs.player.hp = 80
            cs.end_turn()
        assert moves == [
            "BECKON_MOVE", "DE_GAS_MOVE", "GAZE_MOVE", "FADE_MOVE",
            "SCREAM_MOVE", "BECKON_MOVE",
        ]

    def test_beckon_move_adds_status_cards(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        cs.end_turn()  # BECKON: one into the draw pile, one into the discard
        assert cs.player.hp == 80
        beckons = [c for c in cs.player.all_cards if c.id == "beckon"]
        assert len(beckons) == 2
        # One went to the discard; the other went to the draw pile and was
        # drawn into the hand at the next turn start (5-card draw pile).
        assert sum(1 for c in cs.player.discard_pile if c.id == "beckon") == 1
        assert sum(1 for c in cs.player.hand if c.id == "beckon") == 1

    def test_gaze_adds_another_beckon(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        for _ in range(3):  # BECKON, DE_GAS, GAZE
            cs.player.hp = 80
            cs.end_turn()
        assert sum(1 for c in cs.player.all_cards if c.id == "beckon") == 3

    def test_fade_intangible_and_scream(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        fysh = cs.enemy
        for _ in range(4):  # BECKON, DE_GAS, GAZE, FADE
            cs.player.hp = 80
            cs.end_turn()
        assert fysh.powers["intangible"].amount == 1  # ticked once already
        assert DamageCmd.deal(cs.hooks, fysh, 50, dealer=cs.player) == 1
        cs.player.hp = 80
        cs.end_turn()  # SCREAM 13 + Vulnerable 3
        assert cs.player.powers["vulnerable"].amount == 3
        assert "intangible" not in fysh.powers

    def test_beckon_card_hurts_if_kept_in_hand(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        from sts2_rl.cmds import CardPileCmd
        CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("beckon"))
        cs.player.block = 10
        cs.end_turn()
        # 6 unblockable HP loss from the Beckon left in hand (the fysh's own
        # BECKON move deals no damage).
        assert cs.player.hp == 80 - 6

    def test_beckon_card_is_playable_for_one_energy(self):
        cs = fresh_encounter(SOUL_FYSH_BOSS)
        beckon = make_card("beckon")
        from sts2_rl.cmds import CardPileCmd
        CardPileCmd.add_to_hand(cs.hooks, cs.player, beckon)
        energy = cs.player.energy
        assert cs.play_card(cs.player.hand.index(beckon))
        assert cs.player.energy == energy - 1
        assert beckon in cs.player.discard_pile
        cs.end_turn()
        assert cs.player.hp == 80  # played away: no end-of-turn HP loss


# ═════════════════════════════════════════════════════════════════════════
# Waterfall Giant
# ═════════════════════════════════════════════════════════════════════════

class TestWaterfallGiant:
    def test_move_cycle_and_steam_banking(self):
        cs = fresh_encounter(WATERFALL_GIANT_BOSS)
        giant = cs.enemy
        assert giant.max_hp == 240
        moves = []
        for _ in range(7):
            moves.append(giant._current_move.id)
            cs.player.hp = 80
            cs.end_turn()
        assert moves == [
            "PRESSURIZE_MOVE", "STOMP_MOVE", "RAM_MOVE", "SIPHON_MOVE",
            "PRESSURE_GUN_MOVE", "PRESSURE_UP_MOVE", "STOMP_MOVE",
        ]
        # 15 from PRESSURIZE + 3 per move since
        assert giant.powers["steam_eruption"].amount == 15 + 3 * 6

    def test_stomp_and_pressure_gun_scaling(self):
        cs = fresh_encounter(WATERFALL_GIANT_BOSS)
        giant = cs.enemy
        cs.end_turn()  # PRESSURIZE
        cs.end_turn()  # STOMP 15 + Weak 1
        assert cs.player.hp == 65
        assert cs.player.powers["weak"].amount == 1
        assert giant._current_move.id == "RAM_MOVE"
        # PRESSURE_GUN telegraphs 20 and grows by 5 per use
        gun = giant.machine.states["PRESSURE_GUN_MOVE"]
        assert gun.intent.damage == 20
        for _ in range(3):  # RAM, SIPHON, PRESSURE_GUN
            cs.player.hp = 80
            cs.end_turn()
        assert gun.intent.damage == 25

    def test_siphon_heals(self):
        cs = fresh_encounter(WATERFALL_GIANT_BOSS)
        giant = cs.enemy
        for _ in range(3):  # PRESSURIZE, STOMP, RAM
            cs.player.hp = 80
            cs.end_turn()
        DamageCmd.deal(cs.hooks, giant, 30, dealer=cs.player)
        hp = giant.hp
        cs.player.hp = 80
        cs.end_turn()  # SIPHON: heal 10
        assert giant.hp == hp + 10

    def test_killing_blow_triggers_the_explosion(self):
        cs = fresh_encounter(WATERFALL_GIANT_BOSS)
        giant = cs.enemy
        cs.end_turn()  # PRESSURIZE: Steam Eruption 15
        DamageCmd.deal(cs.hooks, giant, 999, dealer=cs.player)
        assert not cs.is_over
        assert giant.is_about_to_blow
        assert giant.hp == 999_999_999
        assert giant.current_intent.move_type == MoveType.STUN
        cs.end_turn()  # ABOUT_TO_BLOW: bank the steam, lose the turn
        assert cs.player.hp == 80
        assert "steam_eruption" not in giant.powers
        intent = giant.current_intent
        assert intent.move_type == MoveType.DEATH_BLOW
        assert intent.damage == 15
        cs.end_turn()  # EXPLODE: 15 damage and the giant dies in the blast
        assert cs.player.hp == 65
        assert cs.is_over and cs.result.player_won

    def test_dies_normally_without_steam_eruption(self):
        # Before PRESSURIZE there is no banked steam: a kill just kills.
        cs = fresh_encounter(WATERFALL_GIANT_BOSS)
        giant = cs.enemy
        DamageCmd.deal(cs.hooks, giant, 999, dealer=cs.player)
        assert giant.is_dead
        assert not giant.is_about_to_blow


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
            "corpse_slugs_weak", "corpse_slugs_normal", "cultists",
            "fossil_stalker", "gremlin_merc", "haunted_ship", "living_fog",
            "punch_construct", "phantasmal_gardeners", "lagavulin_matriarch",
            "seapunk_weak", "seapunk_normal", "sewer_clam", "skulking_colony",
            "sludge_spinner", "soul_fysh", "terror_eel", "toadpoles",
            "two_tailed_rats", "waterfall_giant",
        }


class TestGremlinMercThievery:
    """ThieveryPower.cs / HeistPower.cs / SurprisePower.cs: the Merc steals
    min(20, the player's gold) after each of his attacks (GoldLossType.
    Stolen); his death moves the stolen total onto a HeistPower on the Fat
    Gremlin (SurprisePower.AfterDeath); killing that gremlin before it flees
    queues the gold back as a reward-screen GoldReward (wasGoldStolenBack,
    HeistPower.BeforeDeath); its escape keeps the gold lost."""

    def _run_combat(self, gold, seed=0):
        from sts2_rl.run import RunState
        run = RunState(rng=random.Random(seed))
        run.gold = gold
        return run, run.create_combat(GREMLIN_MERC_NORMAL)

    def test_steal_after_each_attack_settles_on_finish(self):
        run, cs = self._run_combat(gold=100)
        cs.end_turn()  # GIMME, then Steal()
        assert cs.gold_stolen == 20
        assert cs.enemy.powers["thievery"].gold_stolen == 20
        cs.end_turn()  # DOUBLE_SMASH, then Steal()
        assert cs.gold_stolen == 40
        run.finish_combat(cs)
        assert run.gold == 60

    def test_steal_caps_at_available_gold(self):
        run, cs = self._run_combat(gold=15)
        cs.end_turn()
        assert cs.gold_stolen == 15
        cs.end_turn()
        assert cs.gold_stolen == 15  # nothing left to take

    def test_heist_returns_gold_when_fat_gremlin_dies(self):
        from sts2_rl.rooms import RoomType
        run, cs = self._run_combat(gold=100)
        cs.end_turn()  # steal 20
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        fat = cs.enemies[2]
        assert fat.powers["heist"].amount == 20
        DamageCmd.deal(cs.hooks, fat, 999, dealer=cs.player)
        DamageCmd.deal(cs.hooks, cs.enemies[1], 999, dealer=cs.player)
        run.finish_combat(cs, room_type=RoomType.MONSTER)
        assert run.gold == 80  # the theft itself is settled
        gold_before = run.gold
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        # The stolen 20 rides the reward screen on top of the normal
        # Monster gold roll (10-20).
        assert 30 <= rewards.gold <= 40
        assert run.gold == gold_before + rewards.gold

    def test_fled_fat_gremlin_keeps_gold_lost(self):
        run, cs = self._run_combat(gold=100)
        cs.end_turn()  # steal 20
        DamageCmd.deal(cs.hooks, cs.enemies[0], 999, dealer=cs.player)
        fat = cs.enemies[2]
        cs.end_turn()  # gremlins wake up
        cs.end_turn()  # sneaky tackles, fat flees
        assert fat.escaped
        assert cs.pending_reward_extras == []
        run.finish_combat(cs)
        assert run.gold == 80
