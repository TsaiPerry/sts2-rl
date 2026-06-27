"""
Tests for multi-enemy combat: targeting, victory conditions, and turn execution.

Run with:  python -m pytest test/test_multi_enemy.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import StrikeCard, SweepCard
from sts2_rl.cmds import DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter, FuzzyWurmCrawler, Nibbit
from sts2_rl.powers import PoisonPower, ThornsPower, VulnerablePower

TWO_CRAWLERS = Encounter(id="two_crawlers", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler])
CRAWLER_AND_NIBBIT = Encounter(id="crawler_nibbit", monster_classes=[FuzzyWurmCrawler, Nibbit])


def fresh(encounter: Encounter = TWO_CRAWLERS, seed: int = 0) -> CombatState:
    """Combat with a fixed RNG seed and all enemies normalised to 10 HP."""
    cs = CombatState(rng=random.Random(seed), encounter=encounter)
    for e in cs.enemies:
        e.hp = e.max_hp = 10
    cs.player.hand.clear()
    cs.player.hand.extend([StrikeCard() for _ in range(5)])
    cs.player.energy = 10
    return cs


# ══════════════════════════════════════════════════════════════════════════
# Encounter creation
# ══════════════════════════════════════════════════════════════════════════

class TestEncounterCreation:
    def test_two_enemies_are_created(self):
        cs = fresh()
        assert len(cs.enemies) == 2

    def test_enemies_have_correct_hp(self):
        cs = fresh()
        assert cs.enemies[0].hp == 10
        assert cs.enemies[1].hp == 10

    def test_cs_enemy_property_returns_first(self):
        cs = fresh()
        assert cs.enemy is cs.enemies[0]

    def test_mixed_encounter_creates_different_types(self):
        cs = fresh(CRAWLER_AND_NIBBIT)
        assert isinstance(cs.enemies[0], FuzzyWurmCrawler)
        assert isinstance(cs.enemies[1], Nibbit)


# ══════════════════════════════════════════════════════════════════════════
# Targeting via play_card(hand_idx, target_idx)
# ══════════════════════════════════════════════════════════════════════════

class TestTargeting:
    def test_no_target_idx_hits_first_enemy(self):
        cs = fresh()
        cs.play_card(0)
        assert cs.enemies[0].hp == 10 - 6
        assert cs.enemies[1].hp == 10

    def test_target_idx_0_hits_first_enemy(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        assert cs.enemies[0].hp == 10 - 6
        assert cs.enemies[1].hp == 10

    def test_target_idx_1_hits_second_enemy(self):
        cs = fresh()
        cs.play_card(0, target_idx=1)
        assert cs.enemies[0].hp == 10
        assert cs.enemies[1].hp == 10 - 6

    def test_can_target_each_enemy_independently(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        cs.play_card(0, target_idx=1)
        assert cs.enemies[0].hp == 4
        assert cs.enemies[1].hp == 4

    def test_out_of_range_target_idx_falls_back_to_first_living(self):
        cs = fresh()
        cs.play_card(0, target_idx=99)
        assert cs.enemies[0].hp == 10 - 6
        assert cs.enemies[1].hp == 10


# ══════════════════════════════════════════════════════════════════════════
# ctx.enemy convenience property
# ══════════════════════════════════════════════════════════════════════════

class TestCtxEnemyProperty:
    def test_returns_first_enemy_when_both_alive(self):
        cs = fresh()
        ctx = cs._ctx()
        assert ctx.enemy is cs.enemies[0]

    def test_skips_dead_first_enemy(self):
        cs = fresh()
        cs.enemies[0].hp = 0
        ctx = cs._ctx()
        assert ctx.enemy is cs.enemies[1]

    def test_falls_back_to_first_when_all_dead(self):
        cs = fresh()
        cs.enemies[0].hp = 0
        cs.enemies[1].hp = 0
        ctx = cs._ctx()
        assert ctx.enemy is cs.enemies[0]


# ══════════════════════════════════════════════════════════════════════════
# Victory condition — all enemies must die
# ══════════════════════════════════════════════════════════════════════════

class TestVictoryCondition:
    def test_killing_one_enemy_does_not_end_combat(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)       # 10 → 4
        cs.play_card(0, target_idx=0)       # 4 → dead
        assert cs.enemies[0].is_dead
        assert not cs.enemies[1].is_dead
        assert not cs.is_over

    def test_killing_second_enemy_ends_combat(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)       # enemy 0: 10 → 4
        cs.play_card(0, target_idx=0)       # enemy 0: dead
        cs.play_card(0, target_idx=1)       # enemy 1: 10 → 4
        cs.play_card(0, target_idx=1)       # enemy 1: dead → victory
        assert cs.is_over
        assert cs.result.player_won

    def test_killing_both_simultaneously_not_needed(self):
        cs = fresh()
        for _ in range(2):
            cs.play_card(0, target_idx=0)
        assert not cs.is_over
        for _ in range(2):
            cs.play_card(0, target_idx=1)
        assert cs.is_over and cs.result.player_won

    def test_enemy_property_tracks_first_living_after_death(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        cs.play_card(0, target_idx=0)       # enemy 0 dead
        assert cs.enemy is cs.enemies[1]


# ══════════════════════════════════════════════════════════════════════════
# Enemy turn execution — each living enemy acts
# ══════════════════════════════════════════════════════════════════════════

class TestEnemyTurnExecution:
    def test_both_enemies_deal_damage_in_one_round(self):
        cs = fresh()
        hp_before = cs.player.hp
        cs.end_turn()
        # 2 × FuzzyWurmCrawler ACID_GOOP (4 dmg each) = 8 total
        assert cs.player.hp == hp_before - 8

    def test_dead_enemy_skips_its_turn(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        cs.play_card(0, target_idx=0)       # enemy 0 dead before end of turn
        hp_before = cs.player.hp
        cs.end_turn()
        assert cs.player.hp == hp_before - 4   # only enemy 1 attacks (4 dmg)

    def test_each_enemy_block_clears_before_its_turn(self):
        cs = fresh()
        cs.enemies[0].block = 5
        cs.enemies[1].block = 8
        cs.end_turn()
        assert cs.enemies[0].block == 0
        assert cs.enemies[1].block == 0

    def test_poison_kills_one_enemy_other_still_attacks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemies[0], PoisonPower, 20)
        hp_before = cs.player.hp
        cs.end_turn()
        # Enemy 0 died from Poison before attacking; enemy 1 attacked for 4
        assert cs.player.hp == hp_before - 4
        assert cs.enemies[0].is_dead

    def test_poison_kills_last_enemy_triggers_victory(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemies[0], PoisonPower, 20)
        cs.play_card(0, target_idx=1)
        cs.play_card(0, target_idx=1)
        assert not cs.is_over                   # enemy 0 still alive
        cs.end_turn()
        assert cs.is_over
        assert cs.result.player_won

    def test_thorns_kills_both_enemies_triggering_victory(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 10)
        hp_before = cs.player.hp
        cs.end_turn()
        # Each FuzzyWurmCrawler attacked once (4 dmg) before dying to Thorns.
        assert cs.is_over
        assert cs.result.player_won
        assert cs.player.hp == hp_before - 8   # 4 dmg from each crawler

    def test_mixed_encounter_buff_enemy_buffs_self(self):
        cs = fresh(CRAWLER_AND_NIBBIT)
        cs.end_turn()
        # Back Nibbit opens with HISS: applies Strength 2 to itself
        assert cs.enemies[1].powers["strength"].amount == 2

    def test_enemy_rotates_moves_across_rounds(self):
        cs = fresh()
        hp_before = cs.player.hp
        cs.end_turn()   # round 1: both ACID_GOOP → −8
        assert cs.player.hp == hp_before - 8
        cs.end_turn()   # round 2: both INHALE (buff, no damage)
        assert cs.player.hp == hp_before - 8


# ══════════════════════════════════════════════════════════════════════════
# Thorns reflect targeting
# ══════════════════════════════════════════════════════════════════════════

class TestThornsReflect:
    def test_thorns_reflects_only_to_attacker_not_bystander(self):
        cs = fresh(Encounter(id="t", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]))
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.end_turn()
        # Each crawler attacked → took 3 Thorns; neither was hit by the other's reflect.
        assert cs.enemies[0].hp == 7
        assert cs.enemies[1].hp == 7

    def test_thorns_bystander_takes_zero_reflect_damage(self):
        cs = fresh(Encounter(id="t", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]))
        cs.enemies[1].hp = 0   # mark enemy 1 as pre-dead
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.end_turn()
        assert cs.enemies[0].hp == 7
        assert cs.enemies[1].hp == 0


# ══════════════════════════════════════════════════════════════════════════
# ALL_ENEMIES card routing (SweepCard)
# ══════════════════════════════════════════════════════════════════════════

class TestAllEnemiesCard:
    def test_sweep_hits_both_living_enemies(self):
        cs = fresh()
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0)
        assert cs.enemies[0].hp == 10 - 4
        assert cs.enemies[1].hp == 10 - 4

    def test_sweep_skips_already_dead_enemy(self):
        cs = fresh()
        cs.enemies[0].hp = 0
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0)
        assert cs.enemies[0].hp == 0
        assert cs.enemies[1].hp == 10 - 4

    def test_sweep_kills_both_triggers_victory(self):
        cs = fresh(Encounter(id="t", monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]))
        for e in cs.enemies:
            e.hp = e.max_hp = 4
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0)
        assert cs.is_over
        assert cs.result.player_won

    def test_sweep_ignores_caller_target_idx(self):
        cs = fresh()
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0, target_idx=1)
        assert cs.enemies[0].hp == 10 - 4
        assert cs.enemies[1].hp == 10 - 4


# ══════════════════════════════════════════════════════════════════════════
# Dead-enemy target validation for ANY_ENEMY cards
# ══════════════════════════════════════════════════════════════════════════

class TestDeadTargetFallback:
    def test_targeting_dead_enemy_falls_back_to_first_living(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)   # 10 → 4
        cs.play_card(0, target_idx=0)   # enemy 0 dies
        assert cs.enemies[0].is_dead
        cs.play_card(0, target_idx=0)
        assert cs.enemies[1].hp == 10 - 6

    def test_resolve_target_with_dead_index_returns_living(self):
        cs = fresh()
        cs.enemies[0].hp = 0
        ctx = cs._ctx()
        assert ctx.resolve_target(0) is cs.enemies[1]

    def test_resolve_target_with_valid_living_index(self):
        cs = fresh()
        ctx = cs._ctx()
        assert ctx.resolve_target(1) is cs.enemies[1]

    def test_resolve_target_with_none_returns_first_living(self):
        cs = fresh()
        ctx = cs._ctx()
        assert ctx.resolve_target(None) is cs.enemies[0]


# ══════════════════════════════════════════════════════════════════════════
# Debuffs tick once per round (on_enemy_side_end), not per enemy
# ══════════════════════════════════════════════════════════════════════════

class TestDebuffTickRateWithMultipleEnemies:
    def test_vulnerable_ticks_once_per_round_with_two_enemies(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.end_turn()
        assert cs.player.powers["vulnerable"].amount == 2

    def test_two_rounds_reduce_vulnerable_by_two(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 4)
        cs.end_turn()   # round 1: 4 → 3
        cs.end_turn()   # round 2: 3 → 2
        assert cs.player.powers["vulnerable"].amount == 2

    def test_enemy_vulnerable_ticks_once_per_round(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemies[0], VulnerablePower, 3)
        cs.end_turn()
        assert cs.enemies[0].powers["vulnerable"].amount == 2

    def test_per_enemy_turn_end_does_not_tick_debuffs(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.hooks.on_enemy_turn_end(cs.enemies[0])
        cs.hooks.on_enemy_turn_end(cs.enemies[1])
        assert cs.player.powers["vulnerable"].amount == 3
