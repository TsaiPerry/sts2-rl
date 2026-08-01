"""power_cmd/G3 + G4 (-> damage_pipeline/G2): the given/received phase
separation of `PowerCmd.apply`'s power-amount modifier machinery.

C# runs the given-side chain (`Hook.ModifyPowerAmountGiven`, additive-sum
THEN multiplicative-product, gated on `applier != null &&
combatState.ContainsCreature(applier)`) strictly BEFORE the received-side
chain (`Hook.ModifyPowerAmountReceived`, unconditional, a chain of full-value
overrides rather than a fold) — PowerCmd.cs:120-127, Hook.cs:1888-1930. The
sim used to collapse both into one flat, registration-order chain with no
out-list at all (`hooks.py`'s old `modify_power_amount`) and hard-coded
Artifact as a direct block in `PowerCmd.apply`, bypassing the hook-listener
system entirely. This file pins the real machinery: two separate dispatchers,
each with its own `modifiers` out-list gating a companion
`after_modify_power_amount_{given,received}` event, and ArtifactPower /
RuinedHelmet as real `modify_power_amount_received` listeners.

FIX-PASS ADDENDUM (Task 18 review): the companion dispatches above used to
fire BEFORE the power's state was mutated and passed `power=None` always,
and the new-power path's `CanReceivePowers` re-test (PowerCmd.cs:133) never
gated them, even though C#'s entire tail from `ApplyInternal` through both
companion events sits inside that one `if` block. `TestCompanionEventsFire
AfterStateMutationWithTheRealPower` and `TestCanReceivePowersGatesTheCompanions`
pin the fix: the companions now fire after `existing.on_stack(...)` /
after the power is constructed-and-(maybe)-registered, always receive the
real `Power` instance, and are suppressed entirely when the target fails
the mid-pipeline re-test — while the TRAP case (a debuff Artifact zeroes to
exactly 0 via the received chain) still fires both companions with a real,
un-registered power, because `PowerModel.ApplyInternal`'s own `amount==0m`
check (PowerModel.cs:566) is internal to `ApplyInternal` and gates only
attach/registration, not the companion events after it.

Run with:  py -m pytest test/test_power_modifier_phases.py -v
"""
from __future__ import annotations

import random

from sts2_rl import (
    ArtifactPower,
    CombatState,
    PowerCmd,
    StrengthPower,
    VulnerablePower,
    WeakPower,
    make_relic,
)
from sts2_rl.creatures import Creature


def fresh(relics=None, seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed), relics=relics)


# ── Bare test-double listeners ──────────────────────────────────────────
#
# Registered directly via `hooks.register(...)`, the same pattern
# `test_combat_ending_command_guards.py`'s `Flipper` uses: a plain object
# with only the hook methods it needs, no Power/Relic machinery required.

class _GivenAdditiveSpy:
    def __init__(self, delta: int = 0):
        self.delta = delta
        self.calls: list[int] = []

    def modify_power_amount_given_additive(self, power_cls, target, amount, applier):
        self.calls.append(amount)
        return self.delta


class _GivenMultiplicativeSpy:
    def __init__(self, factor: int = 1):
        self.factor = factor
        self.calls: list[int] = []
        self.after_called = False

    def modify_power_amount_given_multiplicative(self, power_cls, target, amount, applier):
        self.calls.append(amount)
        return self.factor

    def after_modify_power_amount_given(self, power) -> None:
        self.after_called = True


class _ReceivedSpy:
    def __init__(self, result=None):
        self.result = result
        self.calls: list[int] = []
        self.after_called = False

    def modify_power_amount_received(self, power_cls, target, amount, applier):
        self.calls.append(amount)
        return self.result

    def after_modify_power_amount_received(self, power) -> None:
        self.after_called = True


class _GivenTracer:
    """A GIVEN-side-only listener that appends a label to a shared list, so
    cross-phase ordering can be observed directly, independent of
    registration order relative to a received-side listener."""

    def __init__(self, trace: list, label: str, factor: int = 1):
        self.trace = trace
        self.label = label
        self.factor = factor

    def modify_power_amount_given_multiplicative(self, power_cls, target, amount, applier):
        self.trace.append(f"{self.label}:given")
        return self.factor


class _ReceivedTracer:
    """A RECEIVED-side-only listener; see `_GivenTracer`."""

    def __init__(self, trace: list, label: str, result=None):
        self.trace = trace
        self.label = label
        self.result = result

    def modify_power_amount_received(self, power_cls, target, amount, applier):
        self.trace.append(f"{self.label}:received")
        return self.result


# ── Given resolves before received, independent of registration order ────

class TestGivenResolvesBeforeReceived:
    def test_wrong_registration_order_still_resolves_given_before_received(self):
        """A received-side listener registered BEFORE a given-side one would
        run first under the old flat, registration-order chain. The real
        machinery is two separately-sequenced dispatches
        (PowerCmd.cs:122-127): given always resolves first regardless."""
        cs = fresh()
        trace: list[str] = []
        received_listener = _ReceivedTracer(trace, "R")
        given_listener = _GivenTracer(trace, "G")
        cs.hooks.register(received_listener)   # registered FIRST
        cs.hooks.register(given_listener)      # registered SECOND
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert trace == ["G:given", "R:received"]


# ── Given side: additive-sum THEN multiplicative-product ─────────────────

class TestGivenChainShape:
    def test_additive_sum_then_multiplicative_product_not_commutative(self):
        """Hook.cs:1888-1912 — the additive pass runs to completion, THEN
        the multiplicative pass runs over its result. Base 3, +5 additive,
        x2 multiplicative: (3 + 5) * 2 = 16. A naive single-pass fold that
        applied the multiplier during the additive walk would produce a
        different number (e.g. 3*2 + 5 = 11)."""
        cs = fresh()
        cs.hooks.register(_GivenAdditiveSpy(delta=5))
        cs.hooks.register(_GivenMultiplicativeSpy(factor=2))
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert cs.player.powers["strength"].amount == 16

    def test_multiplicative_pass_sees_the_additive_passes_own_output(self):
        """The multiplicative listener is handed the RUNNING total (8), not
        the original raw amount (3) — confirms the two passes are chained,
        not each given the same starting value independently."""
        cs = fresh()
        cs.hooks.register(_GivenAdditiveSpy(delta=5))
        mul = _GivenMultiplicativeSpy(factor=1)
        cs.hooks.register(mul)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert mul.calls == [8]


# ── The modifiers out-list gates the companion event ──────────────────────

class TestModifiersOutListGatesTheCompanionEvent:
    def test_a_no_op_given_listener_is_not_in_the_out_list(self):
        """Hook.cs:1905 — `if (num3 != 1m) list.Add(item)`. A factor of 1
        changed nothing, so the listener is never appended, and so never
        gets AfterModifyingPowerAmountGiven."""
        cs = fresh()
        listener = _GivenMultiplicativeSpy(factor=1)
        cs.hooks.register(listener)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert not listener.after_called

    def test_an_active_given_listener_is_in_the_out_list(self):
        cs = fresh()
        listener = _GivenMultiplicativeSpy(factor=2)
        cs.hooks.register(listener)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert listener.after_called

    def test_a_no_op_received_listener_is_not_in_the_out_list(self):
        """Hook.cs:1923-1927 -- `if (item.TryModifyPowerAmountReceived(...))
        { ...; list.Add(item); }`. Returning `None` ("did not apply") means
        never appended, so no AfterModifyingPowerAmountReceived either."""
        cs = fresh()
        listener = _ReceivedSpy(result=None)
        cs.hooks.register(listener)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert not listener.after_called

    def test_an_active_received_listener_is_in_the_out_list(self):
        cs = fresh()
        listener = _ReceivedSpy(result=6)
        cs.hooks.register(listener)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert listener.after_called
        assert cs.player.powers["strength"].amount == 6


# ── The given-side gate: applier absent / applier not in combat ──────────

class TestGivenSideApplierGate:
    def test_applier_none_skips_the_given_chain(self):
        """PowerCmd.cs:123 -- `applier != null && ...`. No applier at all."""
        cs = fresh()
        spy = _GivenMultiplicativeSpy(factor=2)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        assert spy.calls == []
        assert cs.enemy.powers["vulnerable"].amount == 2  # applied, unmodified

    def test_applier_not_in_combat_skips_the_given_chain(self):
        """PowerCmd.cs:123 -- `... && combatState.ContainsCreature(applier)`.
        A creature that was never added to this combat at all."""
        cs = fresh()
        spy = _GivenMultiplicativeSpy(factor=2)
        cs.hooks.register(spy)
        outsider = Creature(10)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=outsider)
        assert spy.calls == []
        assert cs.enemy.powers["vulnerable"].amount == 2

    def test_applier_present_and_in_combat_runs_the_given_chain(self):
        cs = fresh()
        spy = _GivenMultiplicativeSpy(factor=2)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert spy.calls == [2]
        assert cs.enemy.powers["vulnerable"].amount == 4

    def test_the_received_chain_is_unconditional_even_with_no_applier(self):
        """Unlike the given side, the received chain has no applier gate at
        all (Hook.cs:1917-1930) -- it still runs with applier=None."""
        cs = fresh()
        spy = _ReceivedSpy(result=None)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2)
        assert spy.calls == [2]


# ── Artifact: the charge is spent by the companion event, not the modifier ─

class TestArtifactSpendsItsChargeOnlyViaTheCompanionEvent:
    def test_the_modifier_alone_does_not_spend_a_charge(self):
        """ArtifactPower.TryModifyPowerAmountReceived (ArtifactPower.cs:
        17-36) is a pure decision: it reports the zeroed amount, it does not
        touch its own `amount`. `PowerCmd.Decrement(this)` only happens in
        AfterModifyingPowerAmountReceived (:38-41)."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 3)
        artifact = cs.enemy.powers["artifact"]
        result = artifact.modify_power_amount_received(
            VulnerablePower, cs.enemy, 2, cs.player)
        assert result == 0
        assert artifact.amount == 3   # unchanged by the modifier alone

    def test_the_companion_event_is_what_spends_it(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 3)
        artifact = cs.enemy.powers["artifact"]
        artifact.after_modify_power_amount_received(None)
        assert artifact.amount == 2

    def test_end_to_end_one_charge_per_blocked_debuff_via_real_dispatch(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 2)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in cs.enemy.powers
        assert cs.enemy.powers["artifact"].amount == 1
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, 2, applier=cs.player)
        assert "weak" not in cs.enemy.powers
        assert "artifact" not in cs.enemy.powers   # 2nd charge spent, expired

    def test_a_blocked_debuff_registers_no_power_instance(self):
        """PowerModel.ApplyInternal (PowerModel.cs:564-573): a post-modifier
        amount of exactly 0 never calls `Owner.ApplyPowerInternal` -- no
        listener registration happens for a fully-blocked debuff. Artifact
        starts with 5 charges (not 1) so spending one on the block does not
        also expire-and-unregister ARTIFACT itself, which would confound a
        raw listener-count comparison."""
        cs = fresh()
        before = len(cs.hooks._listeners)
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 5)
        after_artifact = len(cs.hooks._listeners)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert len(cs.hooks._listeners) == after_artifact  # no new registration
        assert after_artifact == before + 1                # just Artifact itself
        assert cs.enemy.powers["artifact"].amount == 4      # one charge spent


# ── RuinedHelmet: marked used by the companion event, not the modifier ───

class TestRuinedHelmetMarksUsedOnlyViaTheCompanionEvent:
    def test_the_modifier_alone_does_not_mark_used(self):
        """RuinedHelmet.TryModifyPowerAmountReceived (RuinedHelmet.cs:32-53)
        is a pure decision; `UsedThisCombat = true` only happens in
        AfterModifyingPowerAmountReceived (:55-60)."""
        cs = fresh(relics=[make_relic("ruined_helmet")])
        helmet = cs.relics[0]
        result = helmet.modify_power_amount_received(
            StrengthPower, cs.player, 3, cs.player)
        assert result == 6
        assert helmet._used is False

    def test_the_companion_event_is_what_marks_it(self):
        cs = fresh(relics=[make_relic("ruined_helmet")])
        helmet = cs.relics[0]
        helmet.after_modify_power_amount_received(None)
        assert helmet._used is True

    def test_end_to_end_only_the_first_strength_gain_doubles(self):
        cs = fresh(relics=[make_relic("ruined_helmet")])
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.player)
        assert cs.player.powers["strength"].amount == 6
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
        assert cs.player.powers["strength"].amount == 8   # 6 + 2, not doubled


# ── power_cmd/step6: the raw amount==0 bail (new-power path only) ────────

class TestRawAmountZeroBail:
    def test_a_raw_zero_creates_nothing_on_a_fresh_application(self):
        """PowerCmd.cs:103 -- `amount == 0m -> return`, before any hook runs
        at all, reached only on the 'no existing instance' path."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 0)
        assert "strength" not in cs.player.powers

    def test_a_raw_zero_offset_does_not_refuse_stacking_onto_an_existing_power(self):
        """`ModifyAmount` (the stacking path) has NO `amount == 0m` guard at
        all (PowerCmd.cs:215-271) -- only `Apply(power, target, ...)`'s own
        entry does, and `Apply<T>` never reaches it once an instance already
        exists. A zero OFFSET onto an EXISTING power is not refused."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.player)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 0, applier=cs.player)
        assert cs.player.powers["strength"].amount == 3


# ── Fix pass: companions fire AFTER state mutation, with the real power ──
#
# The review found a real defect in the three tests above's own foundation:
# the companion dispatches used to run BEFORE `existing.on_stack(...)` /
# power construction (PowerCmd.cs:135-152 runs ApplyInternal FIRST, THEN
# both companions; PowerCmd.cs:237-242 runs SetAmount FIRST), and always
# passed `power=None` where C# passes the real, applied `PowerModel`. The
# sim also never gated the companions on the mid-pipeline `CanReceivePowers`
# re-test (PowerCmd.cs:133), even though C#'s entire tail from
# `ApplyInternal` through both companion events sits inside that one `if`.

class _PowerAmountRecordingGivenSpy:
    """A GIVEN-side listener that always changes the amount (so it lands in
    `given_modifiers` and gets the companion call), and records exactly what
    the companion event handed it -- the object AND its `.amount` at that
    moment, to pin that the companion observes POST-application state."""

    def __init__(self, factor: int = 2):
        self.factor = factor
        self.seen_power = "unset"      # distinguishable from a real None
        self.seen_amount = "unset"

    def modify_power_amount_given_multiplicative(self, power_cls, target, amount, applier):
        return self.factor

    def after_modify_power_amount_given(self, power) -> None:
        self.seen_power = power
        self.seen_amount = None if power is None else power.amount


class _PowerAmountRecordingReceivedSpy:
    """RECEIVED-side counterpart of `_PowerAmountRecordingGivenSpy`."""

    def __init__(self, result=None):
        self.result = result
        self.seen_power = "unset"
        self.seen_amount = "unset"

    def modify_power_amount_received(self, power_cls, target, amount, applier):
        return self.result

    def after_modify_power_amount_received(self, power) -> None:
        self.seen_power = power
        self.seen_amount = None if power is None else power.amount


class TestCompanionEventsFireAfterStateMutationWithTheRealPower:
    def test_given_companion_sees_the_final_applied_amount_on_a_fresh_power(self):
        """PowerCmd.cs:135, 148-150 -- `ApplyInternal` (which calls
        `SetAmount`) runs BEFORE `AfterModifyingPowerAmountGiven`. A listener
        reading `power.amount` from inside the companion event must see the
        FINAL post-chain amount (3 * 2 = 6), not the raw pre-chain amount
        (3), and the SAME object now living in `target.powers`."""
        cs = fresh()
        spy = _PowerAmountRecordingGivenSpy(factor=2)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert spy.seen_amount == 6
        assert spy.seen_power is cs.player.powers["strength"]

    def test_received_companion_sees_the_final_applied_amount_on_a_fresh_power(self):
        cs = fresh()
        spy = _PowerAmountRecordingReceivedSpy(result=9)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.enemy)
        assert spy.seen_amount == 9
        assert spy.seen_power is cs.player.powers["strength"]

    def test_received_companion_sees_the_post_stack_total_and_the_same_object(self):
        """The stacking (ModifyAmount) branch mutates via `existing.on_stack`,
        not construction -- the companion must still see the POST-stack
        total (3 + 4 = 7) and identity-match the pre-existing instance."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3, applier=cs.player)
        existing = cs.player.powers["strength"]
        spy = _PowerAmountRecordingReceivedSpy(result=4)
        cs.hooks.register(spy)
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 1, applier=cs.player)
        assert spy.seen_amount == 7
        assert spy.seen_power is existing
        assert spy.seen_power is cs.player.powers["strength"]

    def test_the_companion_gets_a_real_non_none_power_even_when_artifact_zeroes_the_debuff(self):
        """THE TRAP: `PowerModel.ApplyInternal`'s own `amount == 0m` check
        (PowerModel.cs:566) skips `SetAmount`/registration -- it does NOT
        skip the companion events sitting after it, still inside the same
        `if (target.CanReceivePowers)` block (PowerCmd.cs:133-152). A debuff
        Artifact fully blocks must still hand both companions a REAL power
        instance (constructed via `power_cls(...)`, matching C#'s own
        `power = powerModel.ToMutable()` local -- never kept anywhere since
        nothing registers it, but never None either), with `.amount == 0`
        (the fully-resolved, Artifact-zeroed value), and Artifact must still
        spend exactly one charge."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 3)
        given_spy = _PowerAmountRecordingGivenSpy(factor=2)  # 2 -> 4, before Artifact zeroes it
        cs.hooks.register(given_spy)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in cs.enemy.powers          # never registered
        assert cs.enemy.powers["artifact"].amount == 2       # exactly one charge spent
        assert given_spy.seen_power is not None
        assert isinstance(given_spy.seen_power, VulnerablePower)
        assert given_spy.seen_amount == 0                    # the final, Artifact-zeroed amount


# ── Fix pass: CanReceivePowers gates the companions (new-power path only) ─

class TestCanReceivePowersGatesTheCompanions:
    def test_a_target_that_becomes_unhittable_mid_pipeline_gets_no_companion_events(self):
        """PowerCmd.cs:133 wraps `ApplyInternal` THROUGH both companion
        events in one `if (target.CanReceivePowers)`. A listener that flips
        hittability during the received chain (same pattern as
        `test_combat_ending_command_guards.py::TestPowerCmd::
        test_a_mid_pipeline_hittability_change_refuses_the_power`) must
        suppress BOTH companion events on the new-power path, not merely
        suppress construction."""
        cs = fresh()
        target = cs.enemy

        class Flipper:
            def __init__(self):
                self.armed = False

            def modify_power_amount_received(self, power_cls, tgt, amount, applier):
                self.armed = True
                return None  # unchanged -- just observing/arming

            def should_allow_hitting(self, tgt):
                return not self.armed

        detector = _ReceivedSpy(result=2)
        cs.hooks.register(Flipper())
        cs.hooks.register(detector)
        PowerCmd.apply(cs.hooks, target, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in target.powers
        assert not detector.after_called

    def test_the_stacking_path_is_unaffected_by_the_mid_pipeline_recheck(self):
        """`ModifyAmount` (the stacking pipeline) never consults
        `CanReceivePowers` at all (PowerCmd.cs:215-271 has no such call) --
        the same hittability flip that suppresses a NEW power's companions
        must NOT suppress them when re-stacking onto an existing one."""
        cs = fresh()
        target = cs.enemy
        PowerCmd.apply(cs.hooks, target, VulnerablePower, 2, applier=cs.player)

        class Flipper:
            def __init__(self):
                self.armed = False

            def modify_power_amount_received(self, power_cls, tgt, amount, applier):
                self.armed = True
                return None

            def should_allow_hitting(self, tgt):
                return not self.armed

        detector = _ReceivedSpy(result=5)
        cs.hooks.register(Flipper())
        cs.hooks.register(detector)
        PowerCmd.apply(cs.hooks, target, VulnerablePower, 1, applier=cs.player)
        assert detector.after_called
        assert target.powers["vulnerable"].amount == 7  # 2 + 5, replaced offset stacked in
