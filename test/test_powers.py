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
        # STS2: AfterSideTurnEnd fires for side==Enemy unconditionally, no owner
        # check — but a debuff on the player skips its first duration tick
        # (SkipNextDurationTick).
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, VulnerablePower, 3)
        cs.end_turn()
        assert cs.player.powers["vulnerable"].amount == 3  # first tick skipped
        cs.end_turn()
        assert cs.player.powers["vulnerable"].amount == 2  # ticks from then on


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

    def test_skips_the_first_trigger_on_an_ENEMY_owner(self):
        # MOVED 2026-07-29 (round 7, power/ritual/AfterApplied). It used to be
        # `test_skips_first_trigger_when_applied_by_enemy` and pass
        # `applier=cs.enemy` onto the PLAYER, encoding an applier-side test.
        # RitualPower.cs:36-43 consults `base.Owner.IsEnemy` and never looks at
        # the applier -- and every ported Ritual source is a monster buffing
        # itself, which is exactly the case the old test could not express.
        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
        cs = CombatState(rng=random.Random(0),
                         encounter=Encounter("test", [LeafSlimeS]))
        enemy = cs.enemy
        PowerCmd.apply(cs.hooks, enemy, RitualPower, 2, applier=enemy)
        cs.end_turn()
        assert enemy.strength == 0    # first trigger skipped
        cs.end_turn()
        assert enemy.strength == 2    # second trigger fires

    def test_does_not_skip_on_a_PLAYER_owner(self):
        # MOVED with the test above: the player-side direction is unchanged,
        # because C#'s Owner.IsEnemy is false there and so was the old
        # applier-side test -- including when an ENEMY is the applier.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RitualPower, 2, applier=cs.enemy)
        cs.end_turn()
        assert cs.player.strength == 2


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
    # MOVED WHOLESALE 2026-07-29 (round 7, power/curl_up/AfterDamageReceived).
    # Every test in this class used to drive `DamageCmd.deal` directly and
    # assert the block appeared inside the damage hook. CurlUpPower.cs:34-54
    # only LATCHES the triggering card there and grants NOTHING; the block
    # lands in AfterCardPlayed (:56-70), once the whole card play has resolved
    # -- which is what stops the second and later hits of a multi-hit attack
    # being absorbed by block the game has not handed out yet. So the stimulus
    # is now a card PLAY, and the three C# guards the latch carries (a powered
    # attack, a non-null cardSource, no re-latch onto a different card) are
    # pinned alongside.

    @staticmethod
    def _play(cs, card):
        card.on_play(cs._ctx(), target_idx=0)
        cs.hooks.on_card_played(card)

    def test_gains_block_once_the_card_play_finishes(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        hp_before = cs.enemy.hp
        strike = make_card("strike")
        self._play(cs, strike)
        assert cs.enemy.block == 8
        assert cs.enemy.hp == hp_before - 6      # the hit took full damage

    def test_a_multi_hit_attack_is_not_absorbed_mid_card(self):
        # The whole point of the deferral: Twin Strike's second hit must not
        # meet block the game grants only after the card resolves.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        hp_before = cs.enemy.hp
        self._play(cs, make_card("twin_strike"))
        assert cs.enemy.hp == hp_before - 10     # 5 + 5, neither blocked
        assert cs.enemy.block == 8

    def test_one_shot_expires_after_the_card_play(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        self._play(cs, make_card("strike"))
        assert "curl_up" not in cs.enemy.powers

    def test_a_bare_damage_instance_grants_nothing(self):
        # `cardSource == null -> return` (CurlUpPower.cs:44-47): poison, thorns
        # and relic damage never latch.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        DamageCmd.deal(cs.hooks, cs.enemy, 1, dealer=cs.player)
        assert cs.enemy.block == 0
        assert "curl_up" in cs.enemy.powers

    def test_latches_even_when_block_absorbs_the_hit(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, CurlUpPower, 8)
        cs.enemy.block = 100
        self._play(cs, make_card("strike"))
        assert cs.enemy.block == 100 - 6 + 8
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
    They never tick at on_player_turn_end or before_enemy_side_end.

    Debuffs applied to the player skip their FIRST side-end tick (mirrors
    PowerCmd setting SkipNextDurationTick for player-side debuffs); Intangible
    is a buff, so it ticks immediately even on the player."""

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

    def test_no_tick_at_the_enemy_side_end_before_pass(self):
        # EndEnemyTurnInternal opens with Hook.BeforeTurnEnd
        # (CombatManager.cs:1251) and only then dispatches AfterTurnEnd
        # (:1256), which is where AfterSideTurnEnd -- and so every duration
        # tick -- actually lives.
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.before_enemy_side_end()
        for pid in self._IDS:
            assert cs.player.powers[pid].amount == 3, pid
            assert cs.enemy.powers[pid].amount == 3, pid

    def test_both_player_and_enemy_stacks_tick_at_enemy_side_end(self):
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            # Player debuffs skip their first tick; Intangible is a buff.
            expected = 2 if pid == "intangible" else 3
            assert cs.player.powers[pid].amount == expected, pid
            assert cs.enemy.powers[pid].amount == 2, pid

    def test_player_turn_end_then_enemy_side_end_net_one_tick(self):
        # Mirrors what end_turn() does: player turn end fires first, then enemy side end.
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            expected = 2 if pid == "intangible" else 3
            assert cs.player.powers[pid].amount == expected, pid
            assert cs.enemy.powers[pid].amount == 2, pid

    def test_tick_three_times_then_both_expire(self):
        cs = fresh()
        self._apply_all(cs, 3)
        cs.hooks.on_enemy_side_end()  # enemy 3 → 2; player debuffs skip
        cs.hooks.on_enemy_side_end()  # enemy 2 → 1; player debuffs 3 → 2
        cs.hooks.on_enemy_side_end()  # enemy expired; player debuffs 2 → 1
        for pid in self._IDS:
            assert pid not in cs.enemy.powers, pid
        assert "intangible" not in cs.player.powers  # buff: no skip
        for pid in ("vulnerable", "weak", "frail"):
            assert cs.player.powers[pid].amount == 1, pid
        cs.hooks.on_enemy_side_end()  # player debuffs expire one tick later
        for pid in self._IDS:
            assert pid not in cs.player.powers, pid

    def test_asymmetric_amounts_tick_independently(self):
        # Player has 1 stack, enemy has 3 — they expire at different side ends.
        cs = fresh()
        for cls in self._DEBUFFS:
            PowerCmd.apply(cs.hooks, cs.player, cls, 1)
            PowerCmd.apply(cs.hooks, cs.enemy, cls, 3)

        cs.hooks.on_enemy_side_end()
        assert "intangible" not in cs.player.powers  # buff: expired immediately
        for pid in ("vulnerable", "weak", "frail"):
            assert cs.player.powers[pid].amount == 1, f"player {pid} skipped first tick"
        for pid in self._IDS:
            assert cs.enemy.powers[pid].amount == 2, pid

        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert pid not in cs.player.powers, f"player {pid} should have expired"

        cs.hooks.on_enemy_side_end()
        for pid in self._IDS:
            assert pid not in cs.enemy.powers, f"enemy {pid} should have expired"


# ══════════════════════════════════════════════════════════════════════════
# Potion powers (Clarity / Duplication / Gigantification / Buffer /
# Radiance / Demise / Shackling Potion)
# ══════════════════════════════════════════════════════════════════════════

class TestPotionPowers:
    """The seven powers whose only source is a potion (src/Core/Models/Powers)."""

    def test_clarity_draws_one_extra_card_per_stack_turn(self):
        # ClarityPower.cs: ModifyHandDraw +1 (flat, regardless of stacks) and
        # AfterSideTurnStart decrements — the game's side-turn-start hook runs
        # AFTER SetupPlayerTurn's draw (CombatManager.cs:522 vs :654).
        from sts2_rl.powers import ClarityPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ClarityPower, 2)
        cs.end_turn()
        assert len(cs.player.hand) == cs.player.DRAW_PER_TURN + 1
        assert cs.player.powers["clarity"].amount == 1
        cs.end_turn()
        assert len(cs.player.hand) == cs.player.DRAW_PER_TURN + 1
        assert "clarity" not in cs.player.powers
        cs.end_turn()
        assert len(cs.player.hand) == cs.player.DRAW_PER_TURN

    def test_duplication_plays_the_next_card_twice_then_decrements(self):
        # DuplicationPower.cs: ModifyCardPlayCount +1, AfterModifyingCardPlay-
        # Count decrements (fires immediately after the modifier chain, before
        # the plays), AfterSideTurnEnd removes what is left.
        from sts2_rl.powers import DuplicationPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DuplicationPower, 1)
        cs.player.hand = [make_card("strike")]
        cs.player.energy = 3
        before = cs.enemy.hp
        assert cs.play_card(0)
        assert before - cs.enemy.hp == 12          # two Strikes, not one
        assert "duplication" not in cs.player.powers

    def test_duplication_is_removed_at_the_end_of_the_turn(self):
        from sts2_rl.powers import DuplicationPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DuplicationPower, 2)
        # These powers are AfterSideTurnEnd in C# (power/_side_turn_slot),
        # so they moved off the sim's BeforeTurnEnd slot onto
        # after_player_turn_end. end_turn fires both in order.
        cs.hooks.on_player_turn_end(cs.player)
        cs.hooks.after_player_turn_end(cs.player)
        assert "duplication" not in cs.player.powers

    def test_gigantification_triples_the_next_attack_card(self):
        # GigantificationPower.cs: the first powered Attack command from a card
        # the owner plays is ×3 (ModifyDamageMultiplicative 3), then the power
        # decrements at AfterAttack.
        from sts2_rl.powers import GigantificationPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, GigantificationPower, 1)
        cs.player.hand = [make_card("strike"), make_card("strike")]
        cs.player.energy = 3
        before = cs.enemy.hp
        assert cs.play_card(0)
        assert before - cs.enemy.hp == 18          # 6 × 3
        assert "gigantification" not in cs.player.powers
        before = cs.enemy.hp
        assert cs.play_card(0)
        assert before - cs.enemy.hp == 6           # back to normal

    def test_gigantification_ignores_unpowered_damage(self):
        # BeforeAttack/ModifyDamageMultiplicative both gate on
        # DamageProps.IsPoweredAttack().
        from sts2_rl import DamageProps
        from sts2_rl.powers import GigantificationPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, GigantificationPower, 1)
        before = cs.enemy.hp
        DamageCmd.deal(
            cs.hooks, cs.enemy, 10, dealer=cs.player,
            props=DamageProps.NON_CARD_UNPOWERED,
        )
        assert before - cs.enemy.hp == 10
        assert cs.player.powers["gigantification"].amount == 1

    def test_buffer_prevents_one_instance_of_hp_loss(self):
        # BufferPower.cs: ModifyHpLostAfterOstyLate → 0, then
        # AfterModifyingHpLostAfterOsty decrements (only listeners that
        # actually changed the amount are notified).
        from sts2_rl.powers import BufferPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, BufferPower, 1)
        hp = cs.player.hp
        DamageCmd.deal(cs.hooks, cs.player, 15, dealer=cs.enemy)
        assert cs.player.hp == hp
        assert "buffer" not in cs.player.powers
        DamageCmd.deal(cs.hooks, cs.player, 15, dealer=cs.enemy)
        assert cs.player.hp == hp - 15

    def test_buffer_survives_a_fully_blocked_hit(self):
        # No HP was lost, so nothing reduced it — the stack is untouched.
        from sts2_rl.powers import BufferPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, BufferPower, 1)
        cs.player.block = 20
        DamageCmd.deal(cs.hooks, cs.player, 15, dealer=cs.enemy)
        assert cs.player.powers["buffer"].amount == 1

    def test_radiance_grants_one_energy_at_turn_start_per_stack(self):
        # RadiancePower.cs: AfterEnergyReset → GainEnergy(1) + Decrement.
        from sts2_rl.powers import RadiancePower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RadiancePower, 2)
        cs.end_turn()
        assert cs.player.energy == cs.player.ENERGY_PER_TURN + 1
        assert cs.player.powers["radiance"].amount == 1
        cs.end_turn()
        assert cs.player.energy == cs.player.ENERGY_PER_TURN + 1
        assert "radiance" not in cs.player.powers

    def test_demise_damages_its_owner_every_side_turn_end(self):
        # DemisePower.cs: AfterSideTurnEnd damages the owner for Amount
        # (Unblockable | Unpowered) and does NOT decrement.
        from sts2_rl.powers import DemisePower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, DemisePower, 9, applier=cs.player)
        cs.enemy.block = 50
        before = cs.enemy.hp
        cs.hooks.on_enemy_side_end()
        assert cs.enemy.hp == before - 9           # unblockable
        assert cs.enemy.block == 50
        assert cs.enemy.powers["demise"].amount == 9
        cs.hooks.on_enemy_side_end()
        assert cs.enemy.hp == before - 18

    def test_shackling_potion_power_lowers_strength_until_side_end(self):
        # ShacklingPotionPower : TemporaryStrengthPower with IsPositive=false —
        # -7 Strength now, restored at the end of the owner's side turn.
        from sts2_rl.powers import ShacklingPotionPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ShacklingPotionPower, 7, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == -7
        cs.hooks.on_enemy_side_end()
        assert "strength" not in cs.enemy.powers
        assert "shackling_potion" not in cs.enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# PowerInstanceType (power_cmd/G5)
# ══════════════════════════════════════════════════════════════════════════

class TestPowerInstanceType:
    """PowerCmd.apply's stacking dispatch on PowerInstanceType (power_cmd/G5,
    PowerCmd.cs:165-174 FindExistingInstanceForStacking; PowerModel.cs:144).

    NONE (the default) keeps finding the existing instance by id and
    stacking onto it. INSTANCED never finds one, so a second application
    starts its own independently-ticking instance. INSTANCED_PER_APPLIER
    finds one only when the applier matches.

    Every instance is now REACHABLE: `creature.powers` is C#'s ordered
    `List<PowerModel>`, so `.instances(id)` is `GetPowerInstances` and
    `powers[id]` is `GetPower` — a FirstOrDefault, i.e. the OLDEST instance.
    These tests used to read `powers[id]` for "the instance just applied",
    which only worked because the old dict slot was overwritten by the
    newest; they address instances explicitly now."""

    def test_none_type_power_still_merges_into_one_instance(self):
        # Regression guard: PowerInstanceType.NONE is untouched by G5's fix.
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
        first = cs.player.powers["strength"]
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2)
        assert cs.player.powers["strength"] is first
        assert first.amount == 5

    def test_instanced_power_applied_twice_yields_two_independently_ticking_instances(self):
        # AutomationPower.cs:27 InstanceType.Instanced. Two applications 6
        # draws apart used to merge into one instance and fire a single
        # GainEnergy(2) at draw #10; each now keeps its own cards_left and
        # fires its own GainEnergy(1), at draw #10 (instance 1) and draw #16
        # (instance 2, whose own fresh 10-counter starts at its draw-#6
        # creation).
        from sts2_rl.cmds import EnergyCmd
        from sts2_rl.powers import AutomationPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, AutomationPower, 1)
        for _ in range(6):
            cs.hooks.on_card_drawn(None)
        PowerCmd.apply(cs.hooks, cs.player, AutomationPower, 1)
        inst1, inst2 = cs.player.powers.instances("automation")
        assert cs.player.powers["automation"] is inst1   # GetPower == First
        assert inst1.cards_left == 4      # inst1 kept its own progress...
        assert inst2.cards_left == 10     # ...inst2 starts its own, fresh

        energy_events: list[int] = []
        orig_gain = EnergyCmd.gain

        def spy_gain(hooks, target, amount):
            energy_events.append(amount)
            return orig_gain(hooks, target, amount)

        EnergyCmd.gain = staticmethod(spy_gain)
        try:
            for _ in range(4):                      # draw #10 since 1st apply
                cs.hooks.on_card_drawn(None)
            assert energy_events == [1]              # inst1 fires alone
            for _ in range(6):                       # draw #16 since 1st apply
                cs.hooks.on_card_drawn(None)
            assert energy_events == [1, 1]           # inst2 fires alone
        finally:
            EnergyCmd.gain = orig_gain

    def test_instanced_per_applier_same_applier_stacks_different_applier_splits(self):
        # StranglePower.cs:29 InstanceType.InstancedPerApplier.
        from sts2_rl import Creature
        from sts2_rl.powers import StranglePower
        cs = fresh()
        other_applier = Creature(max_hp=40)

        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 3, applier=cs.player)
        first = cs.enemy.powers["strangle"]

        # Same applier -> finds and stacks the existing instance.
        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 2, applier=cs.player)
        assert cs.enemy.powers["strangle"] is first
        assert first.amount == 5

        # A different applier -> a separate instance; the first is left
        # untouched, ticking on its own.
        PowerCmd.apply(cs.hooks, cs.enemy, StranglePower, 4, applier=other_applier)
        held = cs.enemy.powers.instances("strangle")
        assert len(held) == 2 and held[0] is first
        second = held[1]
        assert second.applier is other_applier
        assert second.amount == 4
        assert first.amount == 5

    def test_rolling_boulder_two_applications_deal_independent_growing_damage(self):
        # RollingBoulderPower.cs:24 InstanceType.Instanced. Two C# instances
        # deal 5+5=10 on the next turn and 10+10=20 on the one after (each
        # grows by its own +5); the pre-fix sim held one merged instance
        # (10, then 15, then 20).
        from sts2_rl.powers import RollingBoulderPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, RollingBoulderPower, 5)
        PowerCmd.apply(cs.hooks, cs.player, RollingBoulderPower, 5)
        assert len(cs.player.powers.instances("rolling_boulder")) == 2

        before = cs.enemy.hp
        cs.hooks.on_player_turn_started(cs.player)
        assert before - cs.enemy.hp == 10       # 5 + 5, not a merged 10
        before = cs.enemy.hp
        cs.hooks.on_player_turn_started(cs.player)
        assert before - cs.enemy.hp == 20       # 10 + 10

    def test_toric_toughness_two_applications_track_independent_block_and_duration(self):
        # ToricToughnessPower.cs InstanceType.Instanced. Two C# instances
        # (2 turns @ block 5, 3 turns @ block 9) gain 5+9=14 block for two
        # turns then 9 alone for a third; the pre-fix sim held one merged
        # instance (turn counter 4, block overwritten to 9).
        from sts2_rl.powers import ToricToughnessPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, ToricToughnessPower, 2, applier=cs.player)
        # The card sets the block of the instance it just applied — the
        # NEWEST one (`ToricToughness.cs` dereferences the Apply result).
        cs.player.powers.instances("toric_toughness")[-1].set_block(5)
        PowerCmd.apply(cs.hooks, cs.player, ToricToughnessPower, 3, applier=cs.player)
        cs.player.powers.instances("toric_toughness")[-1].set_block(9)
        assert len(cs.player.powers.instances("toric_toughness")) == 2

        cs.player.block = 0
        cs.hooks.on_block_cleared(cs.player)
        assert cs.player.block == 14            # 5 + 9, both still alive
        cs.player.block = 0
        cs.hooks.on_block_cleared(cs.player)
        assert cs.player.block == 14            # inst1 -> 0 turns left AFTER this grant
        cs.player.block = 0
        cs.hooks.on_block_cleared(cs.player)
        assert cs.player.block == 9             # only inst2 remains
        cs.player.block = 0
        cs.hooks.on_block_cleared(cs.player)
        assert cs.player.block == 0
        assert "toric_toughness" not in cs.player.powers

    def test_panache_two_applications_have_independent_cards_left_counters(self):
        # PanachePower.cs:35 InstanceType.Instanced.
        from sts2_rl.powers import PanachePower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, PanachePower, 4)
        strike = make_card("strike")
        for _ in range(4):                      # 1 skipped (self) + 3 counted
            cs.hooks.on_card_played(strike)
        PowerCmd.apply(cs.hooks, cs.player, PanachePower, 4)
        inst1, inst2 = cs.player.powers.instances("panache")
        assert inst1.cards_left == 2            # 5 - 3
        assert inst2.cards_left == 5            # fresh, its own play not yet skipped

    def test_sandpit_two_applications_are_independent_devour_timers(self):
        # SandpitPower.cs:37 InstanceType.Instanced: either of two
        # independent timers eats the player when IT runs out.
        from sts2_rl.powers import SandpitPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 2, applier=cs.enemy)
        inst1, inst2 = cs.enemy.powers.instances("sandpit")
        assert inst1.amount == 4 and inst2.amount == 2

        cs.hooks.after_enemy_side_start()       # tick 1: 4->3, 2->1
        assert not cs.player.is_dead
        cs.hooks.after_enemy_side_start()       # tick 2: 3->2, 1->0 -> eaten
        assert cs.player.is_dead

    def test_frantic_escape_modifies_the_existing_sandpit_instance_directly(self):
        # FranticEscape.cs:38-42 bypasses Apply/FindExistingInstanceForStacking
        # entirely (ModifyAmount straight on the found instance), which is
        # what keeps it correct now that Sandpit is Instanced.
        from sts2_rl.powers import SandpitPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, SandpitPower, 4, applier=cs.enemy)
        inst = cs.enemy.powers["sandpit"]
        cs.player.hand = [make_card("frantic_escape")]
        cs.player.energy = 3
        assert cs.play_card(0)
        assert cs.enemy.powers["sandpit"] is inst   # same instance, not a new one
        assert inst.amount == 5                      # +1, not a fresh amount=1

    def test_thievery_two_applications_are_independent_gold_counters(self):
        # ThieveryPower.cs:17 InstanceType.Instanced.
        from sts2_rl.powers import ThieveryPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ThieveryPower, 20, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, ThieveryPower, 10, applier=cs.enemy)
        inst1, inst2 = cs.enemy.powers.instances("thievery")
        assert inst1.amount == 20 and inst2.amount == 10

    def test_heist_two_applications_are_independent_amounts(self):
        # HeistPower.cs:15 InstanceType.Instanced.
        from sts2_rl.powers import HeistPower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, HeistPower, 15, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, HeistPower, 25, applier=cs.enemy)
        inst1, inst2 = cs.enemy.powers.instances("heist")
        assert inst1.amount == 15 and inst2.amount == 25

    def test_withering_presence_two_applications_have_independent_card_counters(self):
        # WitheringPresencePower.cs:26 InstanceType.Instanced.
        from sts2_rl.powers import WitheringPresencePower
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, WitheringPresencePower, 6, applier=cs.enemy)
        PowerCmd.apply(cs.hooks, cs.enemy, WitheringPresencePower, 3, applier=cs.enemy)
        inst1, inst2 = cs.enemy.powers.instances("withering_presence")
        assert inst1._cards_left == 6 and inst2._cards_left == 3

    def test_every_c_sharp_instanced_power_declares_it(self):
        """The two powers that used to hold a hand-rolled substitute for
        instancing (The Bomb's `bombs` fuse list, Swipe's `stolen_cards`
        bucket) declare the real dispatch now — those workarounds existed
        only because `Creature.powers` was a dict with one slot per id.
        C#: TheBombPower.cs:23, SwipePower.cs:23."""
        from sts2_rl.powers import PowerInstanceType, SwipePower, TheBombPower
        assert TheBombPower.instance_type is PowerInstanceType.INSTANCED
        assert SwipePower.instance_type is PowerInstanceType.INSTANCED
