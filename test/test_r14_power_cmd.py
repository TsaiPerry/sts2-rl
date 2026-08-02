"""Round 14, lane R9 — power-command tier: death prevention, InstanceType,
and the pile-resolution chain.

Covers: power/adaptable/g5, power/illusion/g6, power/the_bomb/InstanceType,
power/nostalgia/g8, power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath.

Run with:  py -m pytest test/test_r14_power_cmd.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.combat import CombatState
from sts2_rl.cards import CardType, make_card
from sts2_rl.cmds import CardCmd, CreatureCmd, PowerCmd


def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


# ══════════════════════════════════════════════════════════════════════════
# power/adaptable/g5, power/illusion/g6 — STALE-ALREADY-FIXED
#
# The record frames both as "the prevention branch's HP contract" (sim
# hp=1 vs C# leaving the creature at 0 and re-entering
# KillWithoutCheckingWinCondition). But neither AdaptablePower.cs nor
# IllusionPower.cs overrides Hook.ShouldDie at all -- they only override
# ShouldCreatureBeRemovedFromCombatAfterDeath (AdaptablePower.cs:58-66,
# IllusionPower.cs:108-116). That means a killing blow to the owner NEVER
# takes _resolve_death's else-arm (the "prevention" branch with the
# re-entry loop, CreatureCmd.cs:560-572) -- it takes the REAL-death arm
# (:505-559): InvokeDiedEvent, on_death(target, False), and the corpse is
# merely kept in combat instead of removed. The revive itself is a
# separate, later, explicit CreatureCmd.Heal call from the monster's own
# REVIVE move (IllusionPower.cs:125-134) / TriggerDeadState
# (AdaptablePower.cs:32-39). So the record's "remaining" concern (no
# re-entry modelled) is real for TRUE preventers (Fairy in a Bottle etc,
# out of this lane's scope) but does not apply to these two units at all.
# ══════════════════════════════════════════════════════════════════════════

class TestAdaptableIllusionDeathIsReal:
    def test_adaptable_owner_death_is_the_real_arm_not_prevention(self):
        from sts2_rl.monsters.glory.test_subject import TestSubject
        from sts2_rl.monsters import Encounter
        cs = fresh(seed=1, encounter=Encounter("test", [TestSubject]))
        enemy = cs.enemy
        assert "adaptable" in enemy.powers
        seen = []
        orig = cs.hooks.on_death
        def spy(target, was_removal_prevented=False):
            seen.append((target is enemy, was_removal_prevented))
            return orig(target, was_removal_prevented)
        cs.hooks.on_death = spy
        CreatureCmd.kill(cs.hooks, enemy)
        # The real-death arm fires on_death(enemy, False) -- NOT the
        # prevention arm's on_death(enemy, True).
        assert (True, False) in seen
        assert (True, True) not in seen
        # Corpse stays at 0 HP (no floor-to-1) and stays in combat.
        assert enemy.hp == 0
        assert enemy.is_dead
        assert not enemy.is_removed_from_combat
        assert "adaptable" in enemy.powers  # ShouldPowerBeRemovedAfterOwnerDeath=False

    def test_illusion_owner_death_is_the_real_arm_not_prevention(self):
        from sts2_rl.powers import IllusionPower
        cs = fresh(seed=1)
        enemy = cs.enemy
        PowerCmd.apply(cs.hooks, enemy, IllusionPower, 1)
        CreatureCmd.kill(cs.hooks, enemy)
        assert enemy.hp == 0
        assert enemy.is_dead
        assert not enemy.is_removed_from_combat
        illusion = enemy.powers["illusion"]
        assert illusion.is_reviving

    def test_prevention_branch_else_arm_leaves_creature_dead_no_reentry(self):
        """Sanity check on the OTHER (prevention) branch's current shape,
        used to confirm g5/g6 never reach it: a listener that vetoes
        should_die without healing leaves the creature dead at 0 HP with no
        re-entry loop (the gap the record's "WHAT REMAINS" describes, but it
        belongs to true preventers, not Adaptable/Illusion)."""
        cs = fresh(seed=1)
        enemy = cs.enemy

        class _MutePreventer:
            def should_die(self, target):
                return False if target is enemy else None

        cs.hooks.register(_MutePreventer())
        CreatureCmd.kill(cs.hooks, enemy)
        assert enemy.hp == 0
        assert enemy.is_dead
        assert enemy.retained_after_death


# ══════════════════════════════════════════════════════════════════════════
# power/the_bomb/InstanceType — CLOSED (phase 0 of
# prompts/entity-obs-schema.md). `Creature.powers` is C#'s ordered
# `List<PowerModel>` now, so `PowerInstanceType.Instanced` gives The Bomb the
# two real instances the round-14 witness below could only assert the absence
# of. The `bombs` fuse-list workaround is retired.
# ══════════════════════════════════════════════════════════════════════════

class TestTheBombInstanceType:
    def test_two_fuses_are_two_power_instances(self):
        """The record's own witness, now inverted: play The Bomb, end turn,
        play it again. C# holds TWO TheBombPower instances (Amount 2 and
        Amount 3) -- and so does the sim."""
        from sts2_rl.cards import make_card
        cs = fresh(seed=2)
        cs.player.energy = 10
        card1 = make_card("the_bomb")
        cs.player.hand.append(card1)
        assert cs.play_card(len(cs.player.hand) - 1, None)
        assert "the_bomb" in cs.player.powers
        assert [p.amount for p in cs.player.powers.instances("the_bomb")] == [3]

        cs.end_turn()  # back to player turn: ticks the fuse down to 2

        card2 = make_card("the_bomb")
        cs.player.energy = 10
        cs.player.hand.append(card2)
        assert cs.play_card(len(cs.player.hand) - 1, None)

        # TWO power-list entries, exactly as C# tracks them.
        fuses = cs.player.powers.instances("the_bomb")
        assert [p.amount for p in fuses] == [2, 3]
        assert cs.player.powers.values().count(fuses[0]) == 1
        # `GetPower` is a FirstOrDefault: the OLDEST fuse.
        assert cs.player.powers["the_bomb"] is fuses[0]

    def test_each_instance_explodes_on_its_own_fuse_for_its_own_damage(self):
        """A plain and an upgraded Bomb armed a turn apart detonate a turn
        apart, each for the damage ITS OWN card set — the per-instance
        `DynamicVars.Damage` that `SetDamage` writes (TheBombPower.cs:32-36).
        The retired `bombs` workaround got the damage right; what it could not
        do is hold the two fuses as two powers."""
        from sts2_rl.cards import make_card
        cs = fresh(seed=3)
        cs.enemy.max_hp = cs.enemy.hp = 500      # survive both blasts
        plain, upgraded = make_card("the_bomb"), make_card("the_bomb")
        upgraded.upgrade()

        play(cs, plain)                          # 3 turns, 40 damage
        cs.end_turn()                            # plain 3 -> 2
        play(cs, upgraded)                       # 3 turns, 50 damage
        assert [p.damage for p in cs.player.powers.instances("the_bomb")] == [40, 50]
        cs.end_turn()                            # plain 2 -> 1, upgraded 3 -> 2

        hp = cs.enemy.hp
        cs.end_turn()                            # plain detonates
        assert hp - cs.enemy.hp == 40
        assert [p.damage for p in cs.player.powers.instances("the_bomb")] == [50]

        hp = cs.enemy.hp
        cs.end_turn()                            # upgraded detonates
        assert hp - cs.enemy.hp == 50
        assert "the_bomb" not in cs.player.powers


# ══════════════════════════════════════════════════════════════════════════
# power/nostalgia/g8 — STALE-ALREADY-FIXED
#
# The record (dated 2026-08-01, round 13 R3) says Corruption "reaches into
# the piles by hand" in on_card_played, after Nostalgia/Rebound's chain
# redirect already ran, so Corruption's Skill-exhaust loses the race.
# CorruptionPower (powers.py:912-955) no longer has an on_card_played
# method at all -- round 13 R5 moved it onto the SAME
# modify_card_play_result_pile chain Nostalgia and Rebound use
# (combat.py:1027, before the play-count loop, matching CardModel.cs:1890).
# Because Corruption's listener returns "exhaust" UNCONDITIONALLY for any
# Skill regardless of the incoming pile, and Nostalgia/Rebound's listeners
# both abstain the moment pile != "discard", the final answer is "exhaust"
# for every Skill with Corruption applied REGARDLESS of chain order -- so
# the order-dependent contention the record describes is closed.
# ══════════════════════════════════════════════════════════════════════════

class TestNostalgiaCorruptionReboundChain:
    def test_corruption_wins_regardless_of_listener_order(self):
        from sts2_rl.powers import CorruptionPower, NostalgiaPower, ReboundPower
        for order in (
            (CorruptionPower, NostalgiaPower),
            (NostalgiaPower, CorruptionPower),
        ):
            cs = fresh(seed=3)
            for cls in order:
                amt = 3 if cls is NostalgiaPower else 1
                PowerCmd.apply(cs.hooks, cs.player, cls, amt)
            defend = make_card("defend")  # Skill
            play(cs, defend)
            assert defend in cs.player.exhaust_pile, (
                f"order={[c.__name__ for c in order]}: Corruption must win"
            )
            assert defend not in cs.player.draw_pile
            assert defend not in cs.player.discard_pile

    def test_corruption_and_rebound_both_present_skill_still_exhausts(self):
        from sts2_rl.powers import CorruptionPower, ReboundPower
        cs = fresh(seed=4)
        PowerCmd.apply(cs.hooks, cs.player, ReboundPower, 3)
        PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1)
        defend = make_card("defend")
        play(cs, defend)
        assert defend in cs.player.exhaust_pile
        # Rebound was applied first, so its listener ran while the pile was
        # still "discard" and it ticks its own stack -- Corruption's
        # listener then overrides the FINAL pile to exhaust anyway. Same
        # final pile, order-dependent stack, exactly as the docstring
        # (ReboundPower, powers.py) describes matching Hook.cs:1401-1404.
        assert cs.player.powers["rebound"].amount == 2

    def test_nostalgia_alone_still_redirects_to_draw_top(self):
        """Control: Nostalgia's own effect, unaffected by this fix, still
        works when Corruption is absent."""
        from sts2_rl.powers import NostalgiaPower
        cs = fresh(seed=5)
        PowerCmd.apply(cs.hooks, cs.player, NostalgiaPower, 1)
        defend = make_card("defend")
        play(cs, defend)
        assert cs.player.draw_pile and cs.player.draw_pile[-1] is defend


# ══════════════════════════════════════════════════════════════════════════
# power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath — FIXED
#
# PainfulStabsPower.cs:29-32 implements ShouldCreatureBeRemovedFromCombat-
# AfterDeath the same shape as Adaptable/Illusion (owner stays in combat).
# The sim's PainfulStabsPower never implemented it. It was masked because
# Test Subject always applies PainfulStabs together with AdaptablePower
# (monsters/glory/test_subject.py:134-145), whose OR-veto already keeps the
# corpse. Ported for full fidelity / to remove the latent single-point-of-
# failure -- if anything ever strips Adaptable independently, or the power
# is ever applied to a creature without Adaptable, the corpse retention
# must not silently regress.
# ══════════════════════════════════════════════════════════════════════════

class TestPainfulStabsRetention:
    def test_owner_alone_with_painful_stabs_stays_in_combat_after_death(self):
        from sts2_rl.powers import PainfulStabsPower
        cs = fresh(seed=6)
        enemy = cs.enemy
        PowerCmd.apply(cs.hooks, enemy, PainfulStabsPower, 1)
        assert "adaptable" not in enemy.powers  # isolate the power under test
        CreatureCmd.kill(cs.hooks, enemy)
        assert enemy.is_dead
        assert not enemy.is_removed_from_combat
        assert enemy.retained_after_death

    def test_should_remove_from_combat_after_death_false_for_owner_true_for_others(self):
        from sts2_rl.powers import PainfulStabsPower
        cs = fresh(seed=6)
        enemy = cs.enemy
        power = PowerCmd.apply(cs.hooks, enemy, PainfulStabsPower, 1)
        p = enemy.powers["painful_stabs"]
        assert p.should_remove_from_combat_after_death(enemy) is False
        assert p.should_remove_from_combat_after_death(cs.player) is True
