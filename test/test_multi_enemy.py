"""
Tests for multi-enemy combat: targeting, victory conditions, and turn execution.

Run with:  python -m pytest test/test_multi_enemy.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import StrikeCard, SweepCard
from sts2_rl.cmds import DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter, Intent, Monster, MoveType
from sts2_rl.powers import PoisonPower, ThornsPower, VulnerablePower


# ── Test-only monsters ─────────────────────────────────────────────────────

class MultiHitMonster(Monster):
    """Attacks 3 × 2 damage per turn.  Fixed 10 HP."""
    min_hp = 10
    max_hp = 10

    @property
    def current_intent(self) -> Intent:
        return Intent(move_type=MoveType.ATTACK, damage=2, hits=3)

    def take_turn(self, ctx) -> None:
        self._execute_attack(ctx, 2, 3)


class AttackMonster(Monster):
    """Attacks the player for 3 damage each turn.  Fixed 10 HP."""
    min_hp = 10
    max_hp = 10

    @property
    def current_intent(self) -> Intent:
        return Intent(move_type=MoveType.ATTACK, damage=3, hits=1)

    def take_turn(self, ctx) -> None:
        DamageCmd.deal(ctx.hooks, ctx.player, 3, dealer=self)


class BuffMonster(Monster):
    """Applies Vulnerable(3) to the player each turn.  Fixed 8 HP."""
    min_hp = 8
    max_hp = 8

    @property
    def current_intent(self) -> Intent:
        return Intent(move_type=MoveType.BUFF, buffs=[(VulnerablePower, 3)])

    def take_turn(self, ctx) -> None:
        # Apply 3 stacks so that after the on_enemy_turn_end tick (3→2),
        # Vulnerable is still visible and testable.
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, 3)


TWO_ATTACKERS = Encounter(id="two_attack", monster_classes=[AttackMonster, AttackMonster])
ATTACKER_AND_BUFFER = Encounter(id="atk_buf", monster_classes=[AttackMonster, BuffMonster])


def fresh(encounter: Encounter = TWO_ATTACKERS, seed: int = 0) -> CombatState:
    """Combat with 5 Strike cards in hand and ample energy."""
    cs = CombatState(rng=random.Random(seed), encounter=encounter)
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
        cs = fresh(ATTACKER_AND_BUFFER)
        assert isinstance(cs.enemies[0], AttackMonster)
        assert isinstance(cs.enemies[1], BuffMonster)


# ══════════════════════════════════════════════════════════════════════════
# Targeting via play_card(hand_idx, target_idx)
# ══════════════════════════════════════════════════════════════════════════

class TestTargeting:
    def test_no_target_idx_hits_first_enemy(self):
        cs = fresh()
        cs.play_card(0)                     # target_idx omitted
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
        cs.play_card(0, target_idx=0)       # enemy 0: 10 → 4
        cs.play_card(0, target_idx=1)       # enemy 1: 10 → 4
        assert cs.enemies[0].hp == 4
        assert cs.enemies[1].hp == 4

    def test_out_of_range_target_idx_falls_back_to_first_living(self):
        cs = fresh()
        cs.play_card(0, target_idx=99)      # no enemy 99 → first living (enemies[0])
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
        cs.enemies[0].hp = 0               # mark dead directly
        ctx = cs._ctx()
        assert ctx.enemy is cs.enemies[1]

    def test_falls_back_to_first_when_all_dead(self):
        cs = fresh()
        cs.enemies[0].hp = 0
        cs.enemies[1].hp = 0
        ctx = cs._ctx()
        assert ctx.enemy is cs.enemies[0]  # graceful fallback


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
        # Sequential kills are fine; victory triggers on the last death
        cs = fresh()
        for _ in range(2):
            cs.play_card(0, target_idx=0)   # kill enemy 0
        assert not cs.is_over
        for _ in range(2):
            cs.play_card(0, target_idx=1)   # kill enemy 1
        assert cs.is_over and cs.result.player_won

    def test_enemy_property_tracks_first_living_after_death(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        cs.play_card(0, target_idx=0)       # enemy 0 dead
        assert cs.enemy is cs.enemies[1]    # property now points to enemy 1


# ══════════════════════════════════════════════════════════════════════════
# Enemy turn execution — each living enemy acts
# ══════════════════════════════════════════════════════════════════════════

class TestEnemyTurnExecution:
    def test_both_enemies_deal_damage_in_one_round(self):
        cs = fresh()
        hp_before = cs.player.hp
        cs.end_turn()
        # 2 × AttackMonster (3 dmg each) = 6 total; no player block
        assert cs.player.hp == hp_before - 6

    def test_dead_enemy_skips_its_turn(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)
        cs.play_card(0, target_idx=0)       # enemy 0 dead before end of turn
        hp_before = cs.player.hp
        cs.end_turn()
        assert cs.player.hp == hp_before - 3   # only enemy 1 attacks

    def test_each_enemy_block_clears_before_its_turn(self):
        cs = fresh()
        cs.enemies[0].block = 5
        cs.enemies[1].block = 8
        cs.end_turn()
        assert cs.enemies[0].block == 0
        assert cs.enemies[1].block == 0

    def test_poison_kills_one_enemy_other_still_attacks(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemies[0], PoisonPower, 20)  # fatal on turn start
        hp_before = cs.player.hp
        cs.end_turn()
        # Enemy 0 died from Poison before attacking; enemy 1 attacked for 3
        assert cs.player.hp == hp_before - 3
        assert cs.enemies[0].is_dead

    def test_poison_kills_last_enemy_triggers_victory(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemies[0], PoisonPower, 20)
        # Kill enemy 1 before the turn ends
        cs.play_card(0, target_idx=1)
        cs.play_card(0, target_idx=1)
        assert not cs.is_over                   # enemy 0 still alive
        cs.end_turn()
        # Enemy 1 already dead; enemy 0 dies from Poison → all dead → victory
        assert cs.is_over
        assert cs.result.player_won

    def test_thorns_kills_both_enemies_triggering_victory(self):
        # ThornsPower(10) reflects 10 to every attacker; both 10-HP enemies die.
        # Verifies that after enemy 0 dies mid-turn, the loop continues
        # and enemy 1 still takes its turn (and also dies from Thorns).
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 10)
        hp_before = cs.player.hp
        cs.end_turn()
        # Each enemy attacked once (3 dmg) before being reflected to death.
        assert cs.is_over
        assert cs.result.player_won
        assert cs.player.hp == hp_before - 6   # 3 dmg from enemy 0 + 3 from enemy 1

    def test_mixed_encounter_buff_enemy_applies_debuff_to_player(self):
        cs = fresh(ATTACKER_AND_BUFFER)
        cs.end_turn()
        # BuffMonster applied Vulnerable(3); on_enemy_side_end ticked it once to 2.
        assert cs.player.powers["vulnerable"].amount == 2

    def test_multiple_rounds_accumulate_damage(self):
        cs = fresh()
        hp_before = cs.player.hp
        cs.end_turn()   # round 1: -6
        cs.end_turn()   # round 2: -6
        assert cs.player.hp == hp_before - 12


# ══════════════════════════════════════════════════════════════════════════
# Thorns reflect targeting and multi-hit interaction
# ══════════════════════════════════════════════════════════════════════════

class TestThornsReflect:
    def test_thorns_reflects_only_to_attacker_not_bystander(self):
        # Two enemies take turns sequentially.  ThornsPower(3) on the player
        # should deal 3 damage to whichever enemy attacked, NOT to the other.
        cs = fresh(Encounter(id="t", monster_classes=[AttackMonster, AttackMonster]))
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.end_turn()
        # Enemy 0 attacked → took 3 Thorns (10 - 3 = 7 HP).
        # Enemy 1 attacked → took 3 Thorns (10 - 3 = 7 HP).
        # Neither was hit by Thorns from the OTHER enemy's attack.
        assert cs.enemies[0].hp == 7
        assert cs.enemies[1].hp == 7

    def test_thorns_bystander_takes_zero_reflect_damage(self):
        # If only ONE enemy attacks (the other is already dead), the dead one
        # must not receive any Thorns damage.
        cs = fresh(Encounter(id="t", monster_classes=[AttackMonster, AttackMonster]))
        cs.enemies[1].hp = 0   # mark enemy 1 as pre-dead
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.end_turn()
        # Enemy 0 attacked → took 3 Thorns → 7 HP.
        # Enemy 1 was already dead and should be unchanged at 0.
        assert cs.enemies[0].hp == 7
        assert cs.enemies[1].hp == 0

    def test_multi_hit_stops_when_attacker_dies_from_thorns(self):
        # MultiHitMonster does 3 hits × 2 damage.  Thorns(15) kills it on
        # the first hit, so only 1 hit should land on the player.
        cs = fresh(Encounter(id="t", monster_classes=[MultiHitMonster]))
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 15)  # fatal on first reflect
        hp_before = cs.player.hp
        cs.end_turn()
        assert cs.enemies[0].is_dead
        # Only 1 of 3 hits landed before the attacker died.
        assert cs.player.hp == hp_before - 2   # 1 hit × 2 damage

    def test_multi_hit_all_hits_land_when_attacker_survives(self):
        # Thorns(1) reflects only 1 damage per hit; MultiHitMonster (10 HP)
        # survives all 3 hits and all 3 hits land on the player.
        cs = fresh(Encounter(id="t", monster_classes=[MultiHitMonster]))
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 1)
        hp_before = cs.player.hp
        cs.end_turn()
        assert not cs.enemies[0].is_dead
        assert cs.enemies[0].hp == 10 - 3      # 3 hits × 1 Thorns each
        assert cs.player.hp == hp_before - 6   # 3 hits × 2 damage each

    def test_multi_hit_partial_hits_when_attacker_dies_on_second(self):
        # Thorns(6) on player: MultiHitMonster (10 HP).
        # Hit 1: player takes 2, Thorns deals 6 → monster at 4 HP, still alive.
        # Hit 2: player takes 2, Thorns deals 6 → monster at -2 HP (dead).
        # Hit 3: should NOT fire because attacker is dead.
        cs = fresh(Encounter(id="t", monster_classes=[MultiHitMonster]))
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 6)
        hp_before = cs.player.hp
        cs.end_turn()
        assert cs.enemies[0].is_dead
        assert cs.player.hp == hp_before - 4   # 2 hits × 2 damage (not 3 hits)


# ══════════════════════════════════════════════════════════════════════════
# Fix 1: ALL_ENEMIES card routing (SweepCard)
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
        cs.enemies[0].hp = 0            # mark dead before playing
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0)
        assert cs.enemies[0].hp == 0   # corpse untouched
        assert cs.enemies[1].hp == 10 - 4

    def test_sweep_kills_both_triggers_victory(self):
        cs = fresh(Encounter(id="t", monster_classes=[AttackMonster, AttackMonster]))
        for e in cs.enemies:
            e.hp = 4                    # one hit from Sweep is lethal
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0)
        assert cs.is_over
        assert cs.result.player_won

    def test_sweep_ignores_caller_target_idx(self):
        # target_idx is meaningless for ALL_ENEMIES cards — both should be hit.
        cs = fresh()
        cs.player.hand.insert(0, SweepCard())
        cs.play_card(0, target_idx=1)   # caller "targets" enemy 1, but Sweep hits all
        assert cs.enemies[0].hp == 10 - 4
        assert cs.enemies[1].hp == 10 - 4


# ══════════════════════════════════════════════════════════════════════════
# Fix 2: Dead-enemy target validation for ANY_ENEMY cards
# ══════════════════════════════════════════════════════════════════════════

class TestDeadTargetFallback:
    def test_targeting_dead_enemy_falls_back_to_first_living(self):
        cs = fresh()
        cs.play_card(0, target_idx=0)   # 10 → 4
        cs.play_card(0, target_idx=0)   # enemy 0 dies
        assert cs.enemies[0].is_dead
        # Now try to target the dead enemy — should redirect to enemies[1]
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
# Fix 3: Debuffs tick once per round (on_enemy_side_end), not per enemy
# ══════════════════════════════════════════════════════════════════════════

class TestDebuffTickRateWithMultipleEnemies:
    def test_vulnerable_ticks_once_per_round_with_two_enemies(self):
        # With 2 enemies, Vulnerable should still tick only once per round —
        # not twice (once per enemy's individual turn end).
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.end_turn()
        assert cs.player.powers["vulnerable"].amount == 2   # 3 → 2, not 3 → 1

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
        # Manually fire on_enemy_turn_end twice (simulating two enemies acting)
        # without firing on_enemy_side_end — debuffs must stay at their initial amount.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.hooks.on_enemy_turn_end(cs.enemies[0])
        cs.hooks.on_enemy_turn_end(cs.enemies[1])
        assert cs.player.powers["vulnerable"].amount == 3  # no tick yet
