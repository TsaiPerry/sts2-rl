"""Tests for Task 19's five `creature_card_cmds` HP/block verbs (tier-2
audit-gap campaign, wave "§2G"):

  A. `CreatureCmd.heal` reports the RAW requested amount, not the clamped
     one, and reports it even at full HP (creature_card_cmds/G5 + step22).
  B. `CreatureCmd.lose_max_hp` routes a max-HP loss through the FULL damage
     pipeline in the C#-mandated order -- unfloored compute, then damage,
     then floor -- so it can now kill (creature_card_cmds/G6 + step28/29).
  C. `BlockCmd.lose_block` -- the missing `LoseBlock` verb
     (creature_card_cmds/step18).
  D. `CreatureCmd.set_current_hp` -- the missing `SetCurrentHp` verb, death
     pipeline included (creature_card_cmds/step23).
  E. `CreatureCmd.set_max_and_current_hp` -- the missing
     `SetMaxAndCurrentHp` verb (creature_card_cmds/step26).

Run with:  py -m pytest test/test_hp_block_verbs.py -v
"""
from __future__ import annotations

import random

from sts2_rl import (
    BlockCmd,
    CombatState,
    CreatureCmd,
    DamageCmd,
    DamageProps,
    ValueProp,
)
from sts2_rl.combat import Phase
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.hive import OVICOPTER_NORMAL, ToughEgg


def _spy_hp_changed(hooks):
    """Register a listener recording every on_hp_changed delta; return the list."""
    seen: list[int] = []

    class Spy:
        def on_hp_changed(self, target, delta):
            seen.append(delta)

    hooks.register(Spy())
    return seen


# ═════════════════════════════════════════════════════════════════════════
# A. Heal reporting (creature_card_cmds/G5 + step22)
# ═════════════════════════════════════════════════════════════════════════

class TestHealReportsTheRawAmount:
    def test_reports_the_raw_requested_amount_not_the_clamped_one(self):
        """CreatureCmd.cs:751-754: healing 20 on a player 3 below max reports
        delta 20 (the clamped restore is only 3)."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=7)
        seen = _spy_hp_changed(cs.hooks)
        healed = CreatureCmd.heal(cs.hooks, cs.player, 20)
        assert healed == 3
        assert cs.player.hp == 10
        assert seen == [20]

    def test_reports_the_amount_even_at_full_hp(self):
        """The sim used to gate the event on `healed > 0`; C# gates on the
        REQUESTED amount, so a full-HP heal still reports +amount."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        seen = _spy_hp_changed(cs.hooks)
        healed = CreatureCmd.heal(cs.hooks, cs.player, 5)
        assert healed == 0
        assert cs.player.hp == 10
        assert seen == [5]

    def test_nonpositive_amount_reports_nothing(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=7)
        seen = _spy_hp_changed(cs.hooks)
        assert CreatureCmd.heal(cs.hooks, cs.player, 0) == 0
        assert seen == []


# ═════════════════════════════════════════════════════════════════════════
# B. lose_max_hp — the headline (creature_card_cmds/G6 + step28/step29)
# ═════════════════════════════════════════════════════════════════════════

class TestLoseMaxHpCanKill:
    def test_witness_10_10_player_losing_30_max_hp_dies(self):
        """The record's own witness: a 10/10 creature losing 30 max HP must
        now DIE (C# deals 30 unblockable damage), where the old sim ended it
        alive at 1/1. The combat must then end the way any other death
        does -- no special-casing, just the normal win-condition poll."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 30)
        assert cs.player.is_dead
        assert cs.player.max_hp == 1                # floored AFTER the kill
        cs._check_win_condition()
        assert cs.is_over
        assert cs.result.player_won is False

    def test_partial_loss_deals_unblockable_damage_through_the_real_pipeline(self):
        """Block must not absorb any of it -- Unblockable is set."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        cs.player.block = 5
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 3)
        assert cs.player.hp == 7
        assert cs.player.max_hp == 7
        assert cs.player.block == 5
        assert not cs.player.is_dead

    def test_order_the_damage_pipeline_sees_the_old_unfloored_max_hp(self):
        """step29: MaxHp floors AFTER the damage, not before. A listener
        firing mid-pipeline (before_damage_received, unconditional -- fires
        even on a killing blow) must still see the OLD MaxHp."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        seen_max_hp: list[int] = []

        class Spy:
            def before_damage_received(self, target, amount, dealer, card, props):
                seen_max_hp.append(target.max_hp)

        cs.hooks.register(Spy())
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 15)   # newMaxHp = -5
        assert seen_max_hp == [10]                  # still the pre-floor value
        assert cs.player.max_hp == 1                 # floored only afterwards
        assert cs.player.is_dead

    def test_amount_le_0_is_a_no_op(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 0)
        assert cs.player.max_hp == 10
        assert cs.player.hp == 10

    def test_new_max_hp_above_current_hp_deals_no_damage_at_all(self):
        """`newMaxHp < CurrentHp` is the only trigger for the Damage call."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=6)
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 2)     # newMaxHp = 8 > 6
        assert cs.player.max_hp == 8
        assert cs.player.hp == 6                            # untouched

    def test_from_card_true_carries_the_move_prop(self):
        """isFromCard: true -> Unblockable|Unpowered|Move (BrightestFlame.cs:31)."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        seen_props: list[ValueProp] = []

        class Spy:
            def on_damage_received(self, target, amount, dealer, card, props):
                seen_props.append(props)

        cs.hooks.register(Spy())
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 3, from_card=True)
        assert seen_props == [DamageProps.CARD_HP_LOSS]
        assert ValueProp.MOVE in seen_props[0]

    def test_from_card_false_carries_no_move_prop(self):
        """isFromCard: false -> Unblockable|Unpowered only (PaperCutsPower.cs:20)."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        seen_props: list[ValueProp] = []

        class Spy:
            def on_damage_received(self, target, amount, dealer, card, props):
                seen_props.append(props)

        cs.hooks.register(Spy())
        CreatureCmd.lose_max_hp(cs.hooks, cs.player, 3, from_card=False)
        assert seen_props == [DamageProps.NON_CARD_HP_LOSS]
        assert ValueProp.MOVE not in seen_props[0]


# ═════════════════════════════════════════════════════════════════════════
# C. BlockCmd.lose_block (creature_card_cmds/step18)
# ═════════════════════════════════════════════════════════════════════════

class TestLoseBlock:
    def test_floors_at_zero_and_refires_after_block_broken_with_no_dealer(self):
        """BurrowedPower.cs:40's `LoseBlock(oldOwner, 999999999m)` shape: a
        huge amount floors block at 0 and re-fires AfterBlockBroken with NO
        dealer/card -- C#'s own 2-arg `Hook.AfterBlockBroken(CombatState,
        creature)` call here, unlike the damage pipeline's 3-arg one."""
        cs = CombatState(rng=random.Random(0))
        cs.player.block = 5
        seen: list[tuple] = []

        class Spy:
            def on_block_broken(self, target, dealer=None, card=None):
                seen.append((target, dealer, card))

        cs.hooks.register(Spy())
        BlockCmd.lose_block(cs.hooks, cs.player, 999999999)
        assert cs.player.block == 0
        assert seen == [(cs.player, None, None)]

    def test_no_event_when_there_was_no_block_to_break(self):
        cs = CombatState(rng=random.Random(0))
        seen = []

        class Spy:
            def on_block_broken(self, target, dealer=None, card=None):
                seen.append(target)

        cs.hooks.register(Spy())
        BlockCmd.lose_block(cs.hooks, cs.player, 10)
        assert cs.player.block == 0
        assert seen == []

    def test_no_event_when_block_survives(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.block = 10
        seen = []

        class Spy:
            def on_block_broken(self, target, dealer=None, card=None):
                seen.append(target)

        cs.hooks.register(Spy())
        BlockCmd.lose_block(cs.hooks, cs.player, 4)
        assert cs.player.block == 6
        assert seen == []

    def test_amount_le_0_is_a_no_op(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.block = 5
        BlockCmd.lose_block(cs.hooks, cs.player, 0)
        assert cs.player.block == 5

    def test_no_op_on_a_dead_target(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        cs.player.block = 5
        cs.player.hp = 0
        BlockCmd.lose_block(cs.hooks, cs.player, 5)
        assert cs.player.block == 5

    def test_no_op_when_combat_is_over_or_ending(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.block = 5
        cs.phase = Phase.COMBAT_OVER
        BlockCmd.lose_block(cs.hooks, cs.player, 5)
        assert cs.player.block == 5


# ═════════════════════════════════════════════════════════════════════════
# D. CreatureCmd.set_current_hp (creature_card_cmds/step23)
# ═════════════════════════════════════════════════════════════════════════

class TestSetCurrentHp:
    def test_reports_the_raw_requested_delta_not_the_clamped_one(self):
        """CreatureCmd.cs:773: the event carries `amount - old`, the RAW
        requested value, even though SetCurrentHpInternal clamps to MaxHp."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=5)
        seen = _spy_hp_changed(cs.hooks)
        CreatureCmd.set_current_hp(cs.hooks, cs.player, 50)
        assert cs.player.hp == 10                    # clamped
        assert seen == [45]                           # 50 - 5, unclamped

    def test_no_event_when_the_amount_equals_current_hp(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=7)
        seen = _spy_hp_changed(cs.hooks)
        CreatureCmd.set_current_hp(cs.hooks, cs.player, 7)
        assert seen == []

    def test_setting_to_zero_runs_the_full_death_pipeline(self):
        """None of the sim's raw HP assignments ran BeforeDeath/ShouldDie/
        AfterDeath/Kill; this verb must."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        died = []

        class Spy:
            def on_death(self, creature, was_removal_prevented=False):
                died.append(was_removal_prevented)

        cs.hooks.register(Spy())
        CreatureCmd.set_current_hp(cs.hooks, cs.player, 0)
        assert cs.player.is_dead
        assert died == [False]

    def test_reviving_a_dead_creature_does_not_touch_the_death_pipeline(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        CreatureCmd.set_current_hp(cs.hooks, cs.player, 0)
        assert cs.player.is_dead
        died = []

        class Spy:
            def on_death(self, creature, was_removal_prevented=False):
                died.append(creature)

        cs.hooks.register(Spy())
        CreatureCmd.set_current_hp(cs.hooks, cs.player, 5)
        assert cs.player.hp == 5
        assert not cs.player.is_dead
        assert died == []


# ═════════════════════════════════════════════════════════════════════════
# E. CreatureCmd.set_max_and_current_hp (creature_card_cmds/step26)
# ═════════════════════════════════════════════════════════════════════════

class TestSetMaxAndCurrentHp:
    def test_sets_both_to_the_same_value(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=6)
        CreatureCmd.set_max_and_current_hp(cs.hooks, cs.player, 25)
        assert cs.player.max_hp == 25
        assert cs.player.hp == 25

    def test_raising_above_current_hp_fires_one_event_from_set_current_hp(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=6)
        seen = _spy_hp_changed(cs.hooks)
        CreatureCmd.set_max_and_current_hp(cs.hooks, cs.player, 25)
        assert seen == [19]                           # 25 - 6

    def test_reducing_below_current_hp_fires_no_event_the_max_clamp_pre_empts_it(self):
        """SetMaxHp runs FIRST and its own CurrentHp clamp (Creature.cs:500)
        already pulls CurrentHp down to the new value; SetCurrentHp's
        old-vs-new compare then sees no change and fires nothing. A subtle
        but genuine consequence of the C#-mandated order, not a sim gap."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        seen = _spy_hp_changed(cs.hooks)
        CreatureCmd.set_max_and_current_hp(cs.hooks, cs.player, 4)
        assert cs.player.max_hp == 4
        assert cs.player.hp == 4
        assert seen == []

    def test_max_hp_le_0_kills_before_set_current_hp_ever_runs(self):
        """CreatureCmd.cs:844-847's own MaxHp<=0 Kill branch fires FIRST,
        inside SetMaxHp -- so by the time SetCurrentHp runs the creature is
        already fully dead, and SetCurrentHp's own trailing `if IsDead: Kill`
        (:775-778) fires again regardless. Two Kill passes for one
        SetMaxAndCurrentHp(amount<=0) is the genuine C# behaviour (mirrored
        here as two _resolve_death passes), not a sim double-count."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        died = []

        class Spy:
            def on_death(self, creature, was_removal_prevented=False):
                died.append(was_removal_prevented)

        cs.hooks.register(Spy())
        CreatureCmd.set_max_and_current_hp(cs.hooks, cs.player, 0)
        assert cs.player.is_dead
        assert cs.player.max_hp == 0
        assert died == [False, False]


# ═════════════════════════════════════════════════════════════════════════
# Migrated call site regressions not already pinned elsewhere
# ═════════════════════════════════════════════════════════════════════════

class TestMaxHpZeroKillBypassesShouldDie:
    """CreatureCmd.cs:844-846's real-death gate is
    `force || creature.MaxHp <= 0 || Hook.ShouldDie(...)` -- a SHORT-CIRCUIT
    OR, so a kill driven by MaxHp reaching 0 never consults ShouldDie at all.
    No death-prevention listener is asked, and none spends a charge.

    Added by the controller after the task review demonstrated the opposite
    behaviour: before the fix, a Lizard Tail attached to the target was
    consulted, vetoed, healed "50% of max_hp" (already floored to 0, so it
    restored nothing), and burned its one charge for no effect -- leaving it
    unavailable for a later, genuinely preventable death.
    """

    def test_a_should_die_listener_is_never_consulted_and_keeps_its_charge(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        asked: list = []

        class Preventer:
            """Vetoes every death it is asked about, and records being asked."""

            def should_die(self, creature):
                asked.append(creature)
                return False

        cs.hooks.register(Preventer())
        CreatureCmd.set_max_and_current_hp(cs.hooks, cs.player, 0)

        assert asked == []                    # never consulted: C#'s short-circuit
        assert cs.player.is_dead
        assert cs.player.max_hp == 0

    def test_an_ordinary_damage_death_still_consults_the_same_listener(self):
        """The bypass is scoped to the MaxHp<=0 branch: a normal lethal hit --
        including the Unblockable one `lose_max_hp` deals before it floors --
        must still be preventable."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        asked: list = []

        class Preventer:
            def should_die(self, creature):
                asked.append(creature)
                return False

        cs.hooks.register(Preventer())
        DamageCmd.deal(cs.hooks, cs.player, 99, dealer=cs.enemy)

        assert asked == [cs.player]           # consulted, and the veto held
        assert cs.player.hp == 0
        assert cs.player.max_hp == 10


class TestOvicopterHatchMigration:
    def test_hatch_fires_on_hp_changed_with_the_same_delta_as_the_old_hand_roll(self):
        """ToughEgg._hatch used to dispatch on_hp_changed by hand
        (`delta = hp - self.hp` computed before either assignment); the
        verb-driven version must produce the identical single event."""
        cs = CombatState(rng=random.Random(0), encounter=OVICOPTER_NORMAL)
        cs.end_turn()  # LAY_EGGS
        egg = next(e for e in cs.enemies if isinstance(e, ToughEgg))
        seen = []

        class Spy:
            def on_hp_changed(self, target, delta):
                if target is egg:
                    seen.append(delta)

        cs.hooks.register(Spy())
        old_hp = egg.hp
        cs.end_turn()  # SMASH; the egg hatches
        assert egg.is_hatched
        assert len(seen) == 1
        assert seen[0] == egg.hp - old_hp
