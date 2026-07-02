"""
Tests for every power in sts2_rl/powers.py.

Run with:  python -m pytest test/test_powers.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import (
    CombatState,
    DamageCmd,
    BlockCmd,
    StrengthCmd,
    PowerCmd,
    StrengthPower,
    DexterityPower,
    VulnerablePower,
    WeakPower,
    FrailPower,
    PoisonPower,
    ThornsPower,
    ArtifactPower,
    BarricadePower,
    IntangiblePower,
    RegenPower,
    RitualPower,
    DemonFormPower,
    FeelNoPainPower,
    DarkEmbracePower,
    EnragePower,
    RupturePower,
    CurlUpPower,
)
from sts2_rl.cards import StrikeCard, DefendCard, WoundCard, make_card
from sts2_rl.cmds import ExhaustCmd


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    """Fresh combat with a fixed RNG seed (9-card starter deck, enemy HP 55–57)."""
    return CombatState(rng=random.Random(seed))


# ══════════════════════════════════════════════════════════════════════════
# Strength
# ══════════════════════════════════════════════════════════════════════════

class TestStrength:
    def test_additive_damage_bonus_to_owner_as_dealer(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player, card=StrikeCard())
        assert cs.enemy.hp == before - 9  # 6 + 3

    def test_does_not_apply_to_unpowered_card(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 3, dealer=cs.player, card=WoundCard())
        assert cs.enemy.hp == before - 3  # is_unpowered=True → no strength

    def test_does_not_apply_when_dealer_is_not_owner(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 4, dealer=cs.enemy)
        assert cs.player.hp == before - 4  # player str not added to enemy's attack

    def test_no_card_arg_counts_as_powered(self):
        # Enemy attacks with card=None → strength should apply
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 7)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 4, dealer=cs.enemy, card=None)
        assert cs.player.hp == before - 11  # 4 + 7

    def test_stacks_additively(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 4)
        assert cs.player.strength == 7

    def test_strength_property_reflects_power_amount(self):
        cs = fresh()
        assert cs.enemy.strength == 0
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 7)
        assert cs.enemy.strength == 7


# ══════════════════════════════════════════════════════════════════════════
# Dexterity
# ══════════════════════════════════════════════════════════════════════════

class TestDexterity:
    def test_adds_flat_block_bonus_to_owner(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 2)
        BlockCmd.apply(cs.hooks, cs.player, 5)
        assert cs.player.block == 7  # 5 + 2

    def test_does_not_apply_to_other_creature(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 2)
        BlockCmd.apply(cs.hooks, cs.enemy, 5)
        assert cs.enemy.block == 5

    def test_stacks_additively(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 2)
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 3)
        BlockCmd.apply(cs.hooks, cs.player, 0)
        assert cs.player.block == 5


# ══════════════════════════════════════════════════════════════════════════
# Vulnerable
# ══════════════════════════════════════════════════════════════════════════

class TestVulnerable:
    def test_target_takes_50_pct_more_damage(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert cs.enemy.hp == before - 15  # int(10 × 1.5) = 15

    def test_does_not_affect_other_target(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 10, dealer=cs.enemy)
        assert cs.player.hp == before - 10  # player not vulnerable

    def test_ticks_down_on_enemy_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        cs.end_turn()
        assert cs.enemy.powers["vulnerable"].amount == 1

    def test_expires_when_reaching_zero(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 1)
        cs.end_turn()
        assert "vulnerable" not in cs.enemy.powers

    def test_ticks_on_enemy_turn_end_regardless_of_owner(self):
        # STS2: AfterSideTurnEnd fires for side==Enemy unconditionally, no owner check
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.end_turn()
        assert cs.player.powers["vulnerable"].amount == 2  # ticked even though player owns it


# ══════════════════════════════════════════════════════════════════════════
# Weak
# ══════════════════════════════════════════════════════════════════════════

class TestWeak:
    def test_dealer_deals_25_pct_less_damage(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 2)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 8, dealer=cs.enemy)
        assert cs.player.hp == before - 6  # int(8 × 0.75) = 6

    def test_does_not_affect_non_owner_dealer(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, WeakPower, 2)
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 8, dealer=cs.enemy)
        assert cs.enemy.hp == before - 8  # enemy is not the weakened dealer

    def test_ticks_down_on_enemy_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 2)
        cs.end_turn()
        assert cs.enemy.powers["weak"].amount == 1

    def test_expires_when_reaching_zero(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 1)
        cs.end_turn()
        assert "weak" not in cs.enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# Frail
# ══════════════════════════════════════════════════════════════════════════

class TestFrail:
    def test_owner_gains_25_pct_less_block(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, FrailPower, 2)
        BlockCmd.apply(cs.hooks, cs.player, 8)
        assert cs.player.block == 6  # int(8 × 0.75) = 6

    def test_does_not_affect_other_creature(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, FrailPower, 2)
        BlockCmd.apply(cs.hooks, cs.enemy, 8)
        assert cs.enemy.block == 8

    def test_ticks_down_on_enemy_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, FrailPower, 2)
        cs.end_turn()
        assert cs.enemy.powers["frail"].amount == 1

    def test_expires_when_reaching_zero(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, FrailPower, 1)
        cs.end_turn()
        assert "frail" not in cs.enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# Poison
# ══════════════════════════════════════════════════════════════════════════

class TestPoison:
    def test_deals_unblockable_damage_on_enemy_turn_start(self):
        cs = fresh()
        cs.enemy.block = 20
        PowerCmd.apply(cs.hooks, cs.enemy, PoisonPower, 5)
        hp_before = cs.enemy.hp
        cs.end_turn()
        # Poison bypasses block; the enemy's block is cleared by normal combat
        # mechanics at the start of the enemy turn (unrelated to Poison).
        assert cs.enemy.hp == hp_before - 5

    def test_decrements_each_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, PoisonPower, 3)
        cs.end_turn()
        assert cs.enemy.powers["poison"].amount == 2
        cs.end_turn()
        assert cs.enemy.powers["poison"].amount == 1
        cs.end_turn()
        assert "poison" not in cs.enemy.powers

    def test_kills_enemy_when_hp_drops_to_zero(self):
        cs = fresh()
        cs.enemy.hp = 3
        PowerCmd.apply(cs.hooks, cs.enemy, PoisonPower, 10)
        cs.end_turn()
        assert cs.is_over
        assert cs.result.player_won

    def test_player_poison_fires_on_player_turn_start(self):
        cs = fresh()
        cs.player.block = 100  # absorb enemy attack so only Poison damages HP
        PowerCmd.apply(cs.hooks, cs.player, PoisonPower, 4)
        hp_before = cs.player.hp
        cs.end_turn()
        # block absorbs enemy attack; block cleared at new turn start; then Poison fires
        assert cs.player.hp == hp_before - 4
        assert cs.player.powers["poison"].amount == 3


# ══════════════════════════════════════════════════════════════════════════
# Thorns
# ══════════════════════════════════════════════════════════════════════════

class TestThorns:
    def test_reflects_damage_to_attacker(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.enemy.hp == enemy_hp_before - 3

    def test_fires_even_when_block_absorbs_hit(self):
        # Thorns hooks on_damage_received (fires after block); still reflects
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        cs.player.block = 100
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.enemy.hp == enemy_hp_before - 3

    def test_no_reflection_without_attacker(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3)
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=None)
        assert cs.enemy.hp == enemy_hp_before  # no dealer → no reflection

    def test_reflection_is_blockable(self):
        # STS2 Thorns deals ValueProp.Unpowered damage: the attacker's block
        # absorbs it (unlike Poison, which is Unblockable).
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 5)
        cs.enemy.block = 100
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.enemy)
        assert cs.enemy.hp == enemy_hp_before  # fully absorbed by block
        assert cs.enemy.block == 95

    def test_reflection_not_boosted_by_attacker_vulnerable(self):
        # Unpowered damage skips the Vulnerable multiplier.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 4)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 3)
        enemy_hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.enemy)
        assert cs.enemy.hp == enemy_hp_before - 4  # 4, not 6


# ══════════════════════════════════════════════════════════════════════════
# Artifact
# ══════════════════════════════════════════════════════════════════════════

class TestArtifact:
    def test_blocks_one_debuff_per_stack(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 2)
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 3)       # blocked, artifact 2→1
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2) # blocked, artifact 1→0 (expires)
        PowerCmd.apply(cs.hooks, cs.enemy, FrailPower, 1)      # lands normally
        assert "weak" not in cs.enemy.powers
        assert "vulnerable" not in cs.enemy.powers
        assert "frail" in cs.enemy.powers
        assert "artifact" not in cs.enemy.powers  # fully consumed

    def test_does_not_block_buffs(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 5)
        assert "strength" in cs.enemy.powers
        assert cs.enemy.powers["artifact"].amount == 1  # artifact intact

    def test_stacks_and_each_stack_blocks_one_debuff(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)  # stacks to 2
        assert cs.enemy.powers["artifact"].amount == 2
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 1)
        assert cs.enemy.powers["artifact"].amount == 1  # consumed 1


# ══════════════════════════════════════════════════════════════════════════
# Barricade
# ══════════════════════════════════════════════════════════════════════════

class TestBarricade:
    def test_block_not_cleared_at_start_of_owner_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1)
        cs.player.block = 15
        # Enemy's first move is ATTACK for 4 → absorbs from player's block
        cs.end_turn()
        assert cs.player.block == 11  # 15 - 4 absorbed; NOT cleared to 0

    def test_other_creature_block_still_clears(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1)
        cs.enemy.block = 10
        cs.end_turn()
        assert cs.enemy.block == 0  # enemy block cleared at start of enemy turn


# ══════════════════════════════════════════════════════════════════════════
# Intangible
# ══════════════════════════════════════════════════════════════════════════

class TestIntangible:
    def test_caps_incoming_damage_at_1(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, IntangiblePower, 1)
        before = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 999, dealer=cs.enemy)
        assert cs.player.hp == before - 1

    def test_cap_applies_to_owner_only(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, IntangiblePower, 1)
        before = cs.enemy.hp
        # Use 10 so the enemy survives; confirms no cap is applied (enemy not intangible)
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        assert cs.enemy.hp == before - 10

    def test_ticks_down_on_enemy_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, IntangiblePower, 2)
        cs.end_turn()
        assert cs.enemy.powers["intangible"].amount == 1

    def test_expires_when_reaching_zero(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, IntangiblePower, 1)
        cs.end_turn()
        assert "intangible" not in cs.enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# Regen
# ══════════════════════════════════════════════════════════════════════════

class TestRegen:
    def test_heals_player_on_player_turn_end(self):
        cs = fresh()
        cs.player.hp = 40
        PowerCmd.apply(cs.hooks, cs.player, RegenPower, 5)
        cs.end_turn()
        # on_player_turn_end: heals 5 → 45; then enemy attacks for 4 → 41
        assert cs.player.hp == 41

    def test_decrements_each_turn(self):
        cs = fresh()
        cs.player.hp = 40
        PowerCmd.apply(cs.hooks, cs.player, RegenPower, 3)
        cs.end_turn()
        assert cs.player.powers["regen"].amount == 2

    def test_expires_after_last_tick(self):
        cs = fresh()
        cs.player.hp = 70
        PowerCmd.apply(cs.hooks, cs.player, RegenPower, 1)
        cs.end_turn()
        assert "regen" not in cs.player.powers

    def test_does_not_overheal(self):
        cs = fresh()
        cs.player.hp = cs.player.max_hp - 1
        PowerCmd.apply(cs.hooks, cs.player, RegenPower, 10)
        cs.end_turn()
        # Healed back to max (then possibly reduced by enemy attack)
        # After on_player_turn_end: hp = max_hp (capped). Then enemy attacks for 4.
        assert cs.player.hp == cs.player.max_hp - 4

    def test_heals_enemy_on_enemy_turn_end(self):
        cs = fresh()
        cs.enemy.hp = 30
        PowerCmd.apply(cs.hooks, cs.enemy, RegenPower, 5)
        cs.end_turn()
        assert cs.enemy.hp == 35


# ══════════════════════════════════════════════════════════════════════════
# Ritual
# ══════════════════════════════════════════════════════════════════════════

class TestRitual:
    def test_gives_strength_on_owner_turn_end(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RitualPower, 3)
        cs.end_turn()  # on_player_turn_end fires Ritual
        assert cs.player.strength == 3

    def test_stacks_strength_each_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RitualPower, 3)
        cs.end_turn()
        assert cs.player.strength == 3
        cs.end_turn()
        assert cs.player.strength == 6

    def test_skips_first_trigger_when_applied_by_enemy(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RitualPower, 2, applier=cs.enemy)
        cs.end_turn()
        assert cs.player.strength == 0  # first trigger skipped
        cs.end_turn()
        assert cs.player.strength == 2  # second trigger fires

    def test_does_not_skip_when_applied_by_self(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RitualPower, 2, applier=cs.player)
        cs.end_turn()
        assert cs.player.strength == 2  # no skip when applied by same side


# ══════════════════════════════════════════════════════════════════════════
# DemonForm
# ══════════════════════════════════════════════════════════════════════════

class TestDemonForm:
    def test_gives_player_strength_at_each_turn_start(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DemonFormPower, 2)
        cs.end_turn()  # end_turn → new player turn start → DemonForm fires
        assert cs.player.strength == 2
        cs.end_turn()
        assert cs.player.strength == 4

    def test_gives_enemy_strength_at_enemy_turn_start(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, DemonFormPower, 3)
        cs.end_turn()  # on_enemy_turn_start fires DemonForm
        assert cs.enemy.strength == 3


# ══════════════════════════════════════════════════════════════════════════
# FeelNoPain
# ══════════════════════════════════════════════════════════════════════════

class TestFeelNoPain:
    def test_gains_block_on_card_exhausted(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, FeelNoPainPower, 4)
        card = make_card("wound")
        cs.player.hand.append(card)
        ExhaustCmd.exhaust(cs.hooks, cs.player, card)
        assert cs.player.block == 4

    def test_triggers_for_each_exhaust(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, FeelNoPainPower, 3)
        for _ in range(2):
            card = make_card("wound")
            cs.player.hand.append(card)
            ExhaustCmd.exhaust(cs.hooks, cs.player, card)
        assert cs.player.block == 6


# ══════════════════════════════════════════════════════════════════════════
# DarkEmbrace
# ══════════════════════════════════════════════════════════════════════════

class TestDarkEmbrace:
    def test_draws_one_card_on_exhaust(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 1)
        draw_before = len(cs.player.draw_pile)
        card = make_card("wound")
        cs.player.hand.append(card)
        ExhaustCmd.exhaust(cs.hooks, cs.player, card)
        assert len(cs.player.draw_pile) == draw_before - 1  # drew 1 from pile

    def test_triggers_for_each_exhaust(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DarkEmbracePower, 1)
        draw_before = len(cs.player.draw_pile)
        for _ in range(2):
            card = make_card("wound")
            cs.player.hand.append(card)
            ExhaustCmd.exhaust(cs.hooks, cs.player, card)
        assert len(cs.player.draw_pile) == draw_before - 2


# ══════════════════════════════════════════════════════════════════════════
# Enrage
# ══════════════════════════════════════════════════════════════════════════

class TestEnrage:
    def test_gains_strength_when_skill_is_played(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, EnragePower, 2)
        cs.player.hand.clear()
        cs.player.hand.append(DefendCard())
        cs.player.energy = 3
        cs.play_card(0)  # Defend is a Skill
        assert cs.player.strength == 2

    def test_does_not_trigger_on_attack_card(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, EnragePower, 2)
        cs.player.hand.clear()
        cs.player.hand.append(StrikeCard())
        cs.player.energy = 3
        cs.play_card(0)  # Strike is an Attack, not a Skill
        assert cs.player.strength == 0

    def test_stacks_strength_on_multiple_skills(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, EnragePower, 2)
        cs.player.energy = 10
        cs.player.hand.clear()  # remove original hand so only DefendCards are present
        for _ in range(3):
            cs.player.hand.append(DefendCard())
        cs.play_card(0)
        cs.play_card(0)
        cs.play_card(0)
        assert cs.player.strength == 6


# ══════════════════════════════════════════════════════════════════════════
# Rupture
# ══════════════════════════════════════════════════════════════════════════

class TestRupture:
    def test_gains_strength_when_hp_is_lost(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RupturePower, 1)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.strength == 1

    def test_does_not_trigger_when_block_absorbs_all_damage(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RupturePower, 1)
        cs.player.block = 100
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy)
        assert cs.player.strength == 0

    def test_triggers_each_time_hp_is_lost(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RupturePower, 1)
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.enemy)
        DamageCmd.deal(cs.hooks, cs.player, 3, dealer=cs.enemy)
        assert cs.player.strength == 2

    def test_triggers_from_poison_damage(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RupturePower, 1)
        PowerCmd.apply(cs.hooks, cs.player, PoisonPower, 4)
        cs.player.block = 100  # absorb enemy attack
        cs.end_turn()  # Poison fires at player turn start
        assert cs.player.strength == 1


# ══════════════════════════════════════════════════════════════════════════
# CurlUp
# ══════════════════════════════════════════════════════════════════════════

class TestCurlUp:
    def test_gains_block_on_first_hit(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        hp_before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)
        # STS2: damage resolves first (no block yet), then block appears via on_damage_received
        assert cs.enemy.block == 8
        assert cs.enemy.hp == hp_before - 1

    def test_one_shot_expires_after_first_hit(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)
        assert "curl_up" not in cs.enemy.powers

    def test_does_not_grant_block_on_second_hit(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)  # hp-1, then block+8 → block=8
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)  # no CurlUp → block absorbs 1 → 7
        assert cs.enemy.block == 7

    def test_triggers_even_when_block_absorbs_hit(self):
        # on_damage_received fires even when hp_lost==0 (dealer is not None check suffices)
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        cs.enemy.block = 100
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)
        # block absorbs 1 → block=99; then on_damage_received → +8 → block=107
        assert cs.enemy.block == 107
        assert "curl_up" not in cs.enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# Cross-power interactions
# ══════════════════════════════════════════════════════════════════════════

class TestInteractions:
    def test_vulnerable_and_weak_multiply(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)  # ×1.5 on target
        PowerCmd.apply(cs.hooks, cs.player, WeakPower, 2)       # ×0.75 on dealer
        before = cs.enemy.hp
        DamageCmd.deal(cs.hooks, cs.enemy, 10, dealer=cs.player)
        # int(10 × 0.75 × 1.5) = int(11.25) = 11
        assert cs.enemy.hp == before - 11

    def test_dexterity_before_frail_multiplicative(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 2)  # +2 additive
        PowerCmd.apply(cs.hooks, cs.player, FrailPower, 1)      # ×0.75 multiplicative
        BlockCmd.apply(cs.hooks, cs.player, 8)
        # (8 + 2) × 0.75 = 7.5 → int = 7
        assert cs.player.block == 7

    def test_strength_not_applied_to_unpowered_burn_card(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 10)
        before = cs.player.hp
        from sts2_rl.cards import BurnCard
        DamageCmd.deal(cs.hooks, cs.player, 2, dealer=None, card=BurnCard())
        assert cs.player.hp == before - 2  # BurnCard is_unpowered; strength ignored

    def test_artifact_does_not_block_strength_applied_via_strength_cmd(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        StrengthCmd.apply(cs.hooks, cs.enemy, 5)  # Strength is a BUFF
        assert cs.enemy.strength == 5
        assert cs.enemy.powers["artifact"].amount == 1  # still here


# ══════════════════════════════════════════════════════════════════════════
# Debuff tick timing — both sides
# ══════════════════════════════════════════════════════════════════════════

class TestDebuffTickTiming:
    """Vulnerable/Weak/Frail/Intangible tick at on_enemy_side_end (once per round)
    for BOTH the player and the enemy, regardless of who owns each stack.
    They never tick at on_player_turn_end or on_enemy_turn_end."""

    _DEBUFFS = [VulnerablePower, WeakPower, FrailPower, IntangiblePower]
    _IDS = ["vulnerable", "weak", "frail", "intangible"]

    def _apply_all(self, cs: CombatState, amount: int) -> None:
        for cls in self._DEBUFFS:
            PowerCmd.apply(cs.hooks, cs.player, cls, amount)
            PowerCmd.apply(cs.hooks, cs.enemy, cls, amount)

    def test_no_tick_at_player_turn_end(self):
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_player_turn_end(cs.player)
        for pid in self._IDS:
            assert cs.player.powers[pid].amount == 3, pid
            assert cs.enemy.powers[pid].amount == 3, pid

    def test_no_tick_at_per_enemy_turn_end(self):
        # on_enemy_turn_end fires per-enemy; debuffs must NOT tick here.
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_enemy_turn_end(cs.enemy)
        for pid in self._IDS:
            assert cs.player.powers[pid].amount == 3, pid
            assert cs.enemy.powers[pid].amount == 3, pid

    def test_both_player_and_enemy_stacks_tick_at_enemy_side_end(self):
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert cs.player.powers[pid].amount == 2, pid
            assert cs.enemy.powers[pid].amount == 2, pid

    def test_player_turn_end_then_enemy_side_end_net_one_tick(self):
        # Mirrors what end_turn() does: player turn end fires first, then enemy side end.
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert cs.player.powers[pid].amount == 2, pid
            assert cs.enemy.powers[pid].amount == 2, pid

    def test_tick_three_times_then_both_expire(self):
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_enemy_side_end()  # 3 → 2
        cs.hooks.on_enemy_side_end()  # 2 → 1
        cs.hooks.on_enemy_side_end()  # 1 → 0 → expired
        for pid in self._IDS:
            assert pid not in cs.player.powers, pid
            assert pid not in cs.enemy.powers, pid

    def test_asymmetric_amounts_tick_independently(self):
        # Player has 1 stack, enemy has 3 — they expire at different side ends.
        cs = fresh()
        for cls in self._DEBUFFS:
            PowerCmd.apply(cs.hooks, cs.player, cls, 1)
            PowerCmd.apply(cs.hooks, cs.enemy, cls, 3)

        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert pid not in cs.player.powers, f"player {pid} should have expired"
            assert cs.enemy.powers[pid].amount == 2, pid

        cs.hooks.on_enemy_side_end()
        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert pid not in cs.enemy.powers, f"enemy {pid} should have expired"
