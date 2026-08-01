"""Task 22 (`monster_state_machine/G8` + `/G7` + `/G2`): construction- and
edge-validation tests for `MonsterMoveStateMachine`.

Three mechanisms, all at machine-BUILD time (none of this runs per-transition,
so the 6.5M-fuzzed-transition dormancy result the record cites is unaffected):

  G8 clause b -- `MonsterModel.MoveStateMachine`'s setter THROWS if a machine
    is already set (MonsterModel.cs:228-236); only ResetStateMachine (:389-392)
    clears it first. `MachineMonster.machine` was a bare attribute; it is now
    a guarded property plus `reset_state_machine()`.
    (G8 clause a -- the duplicate-state-id Dictionary.Add throw -- is ALREADY
    fixed: `MonsterState.register_states` raises ValueError today, pinned by
    test_hook_order.py::TestMonsterStateMachineOrder
    ::test_duplicate_state_id_is_rejected_at_machine_construction, which is a
    real (non-xfail) passing test. Re-verified here, not re-implemented.)

  G8 clause c -- only the AddBranch overload that takes an explicit
    `MoveRepeatType` parameter (never a `maxRepeats` int) throws on
    CanRepeatXTimes, because that overload has no maxRepeats slot
    (RandomBranchState.cs:46-51). The sim has one `add_branch` signature
    instead of ten overloads, so `max_times=None` (not supplied) is now what
    distinguishes that illegal shape from a real, explicit
    `max_times=0` -- which stays LEGAL (RandomBranchState.cs:144-147, step
    21/G7 clause a, a permanently-disabled branch, already fixed and pinned
    by test_hook_order.py
    ::test_max_times_zero_disables_the_branch_instead_of_raising).

  G7 clause c -- the sequential float subtract-and-check loop THROWS on a
    genuine fall-through (RandomBranchState.cs:127); the sim silently
    returned the last branch. Folded into the same fix: the sim ALSO used to
    raise pre-draw on a total weight of exactly 0, which C# does not do --
    `Rng.NextFloat(0f)` doesn't throw, it burns a draw and returns 0f, so the
    FIRST branch's `num <= 0f` check is true immediately
    (RandomBranchState.cs:115-127, Rng.cs:145-164). Removing the sim's
    pre-draw special case fixes BOTH: a genuine fall-through now raises
    (matching C#), and an all-zero weight vector no longer crashes (also
    matching C# -- named as the Flyconid-onto-MachineMonster hazard in the
    task brief).

  G2 -- the game ships a RandomBranchState that is CONSTRUCTED, given real
    branches, and added to the SAME list RegisterStates walks (so it IS in
    `States`), yet nothing ever assigns it as a FollowUpState or an
    initialState (PhrogParasite.cs:39-52's "RAND"). `MonsterMoveStateMachine`
    had no way to register a state without every state in `states` being
    reachable-by-convention; `unreachable_states` is the new, purely additive
    parameter for that. (Inklet.cs:69-81's "INIT_RAND" is a DIFFERENT, more
    extreme shape than the audit record's step 49 describes: `list.Add` is
    never called on it at all, so it never reaches
    `MonsterMoveStateMachine`'s constructor and never enters `States` --
    that needs no dedicated machinery, since simply not passing an object
    anywhere already reproduces it. Only PhrogParasite's shape -- registered
    but unwired -- needed a new parameter. See the report for the full
    correction.)
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.monsters.base import Intent, MoveType
from sts2_rl.monsters.state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)


class _Owner:
    """Minimal stand-in for a MachineMonster, matching the pattern used by
    TestMonsterStateMachineOrder in test_hook_order.py -- a machine's roll
    only reads `owner.machine`."""


class _CountingRandom(random.Random):
    """Counts `.random()` calls, so a test can assert a roll burned exactly
    the draws it should (or none at all)."""

    def __init__(self, seed):
        super().__init__(seed)
        self.floats = 0

    def random(self):
        self.floats += 1
        return super().random()


def _loop_move(state_id: str, damage: int = 1) -> MoveState:
    move = MoveState(state_id, lambda ctx: None, Intent(MoveType.ATTACK, damage=damage))
    move.follow_up = move
    return move


class TestAddBranchRejectsOverloadOnesIllegalShape:
    """G8 clause c (step 22): `add_branch(state, repeat_type=CAN_REPEAT_X_TIMES)`
    with no `max_times` mirrors calling AddBranch's repeatType-only overload
    with CanRepeatXTimes -- the one shape C# rejects outright
    (RandomBranchState.cs:48-51, "Use other constructor to specify number of
    repeats")."""

    def test_can_repeat_x_times_without_max_times_raises(self):
        target = _loop_move("TARGET")
        branch = RandomBranchState("BR")
        with pytest.raises(ValueError):
            branch.add_branch(target, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES)

    def test_can_repeat_x_times_with_explicit_zero_still_builds_a_disabled_branch(self):
        # step 21/G7 clause a is a DIFFERENT, already-legal shape: an
        # EXPLICIT max_times=0 permanently disables the branch instead of
        # raising (RandomBranchState.cs:144-147) -- this guard must not
        # regress that fix.
        a = _loop_move("A")
        b = _loop_move("B")
        branch = RandomBranchState("BR")
        branch.add_branch(b)  # default weight 1.0, CAN_REPEAT_FOREVER
        branch.add_branch(a, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=0)
        for m in (a, b):
            m.follow_up = branch
        machine = MonsterMoveStateMachine([a, b, branch], branch)
        owner = _Owner()
        owner.machine = machine
        rng = random.Random(0)
        ids = {machine.roll_move(owner, rng).id for _ in range(200)}
        assert ids == {"B"}

    def test_other_repeat_types_never_need_max_times(self):
        # CAN_REPEAT_FOREVER / CANNOT_REPEAT / USE_ONLY_ONCE all correspond
        # to C# overloads that take a bare `MoveRepeatType` with no
        # maxRepeats slot AND are legal there (only CanRepeatXTimes is
        # rejected) -- so max_times must stay optional for them.
        target = _loop_move("TARGET")
        branch = RandomBranchState("BR")
        branch.add_branch(target, repeat_type=MoveRepeatType.CAN_REPEAT_FOREVER)
        branch.add_branch(target, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(target, repeat_type=MoveRepeatType.USE_ONLY_ONCE)
        assert len(branch._branches) == 3


class TestMachineSetterGuard:
    """G8 clause b (step 37): `MonsterModel.MoveStateMachine`'s setter throws
    on a second assignment (MonsterModel.cs:228-236); only ResetStateMachine
    (:389-392) clears it first."""

    @staticmethod
    def _make() -> MachineMonster:
        class _Mon(MachineMonster):
            min_hp = 5
            max_hp = 5

            def build_machine(self) -> MonsterMoveStateMachine:
                move = _loop_move("LOOP")
                return MonsterMoveStateMachine([move], move)

        return _Mon(hooks=None, rng=random.Random(0))

    def test_construction_sets_the_machine_exactly_once(self):
        mon = self._make()
        assert mon.machine.current.id == "LOOP"

    def test_rebinding_machine_mid_combat_raises(self):
        mon = self._make()
        replacement = MonsterMoveStateMachine([_loop_move("OTHER")], _loop_move("OTHER"))
        with pytest.raises(RuntimeError):
            mon.machine = replacement
        # The original machine must survive the rejected rebind untouched.
        assert mon.machine.current.id == "LOOP"

    def test_reset_state_machine_allows_a_fresh_rebind(self):
        mon = self._make()
        mon.reset_state_machine()
        replacement = MonsterMoveStateMachine([_loop_move("OTHER")], _loop_move("OTHER"))
        mon.machine = replacement  # no raise: reset cleared the guard
        assert mon.machine.current.id == "OTHER"

    def test_dummy_owner_objects_are_unaffected(self):
        # The guard lives on MachineMonster specifically; test_hook_order.py
        # and test_new_features.py's `_Owner` stand-ins reassign `.machine`
        # freely and must keep doing so (they are plain objects, not
        # MachineMonster instances, so no property is involved).
        owner = _Owner()
        owner.machine = MonsterMoveStateMachine([_loop_move("A")], _loop_move("A"))
        owner.machine = MonsterMoveStateMachine([_loop_move("B")], _loop_move("B"))
        assert owner.machine.current.id == "B"


class TestRandomBranchFallThrough:
    """G7 clause c (step 15): a genuine fall-through (every branch's `num`
    still positive after subtracting all of them) THROWS in C#
    (RandomBranchState.cs:127); the sim used to return the last branch.
    Folded in: the all-zero-weight case, which does NOT throw in C# and must
    not throw in the sim either (RandomBranchState.cs:115-127, Rng.cs:145-164)."""

    def test_fall_through_raises_instead_of_silently_picking_the_last_branch(self):
        # Weights whose sequential subtraction leaves a strictly positive
        # floating-point residual after every weight has been subtracted
        # from a roll scaled to exactly their sum -- a real IEEE754 rounding
        # artifact (found by brute-force search over random float vectors),
        # not a special case the implementation manufactures. Verified by
        # hand: `total = sum(weights)`; `roll = 1.0 * total`; subtracting
        # each weight in order never once satisfies `roll <= 0` until the
        # residual after the LAST one is 2.2737e-13 -- still > 0.
        weights = [732.6853021830817, 820.1747405438164,
                   802.8484131750756, 855.138356333315]
        moves = [_loop_move(f"M{i}") for i in range(len(weights))]
        branch = RandomBranchState("BR")
        for move, w in zip(moves, weights):
            branch.add_branch(move, weight=w)
        machine = MonsterMoveStateMachine(moves, branch)
        owner = _Owner()
        owner.machine = machine

        class _MaxRoll:
            """`_weighted_roll`'s legacy path is `rng.random() * total`; a
            stub returning the supremum of `random.Random.random()`'s real
            range (which never actually reaches 1.0) forces the exact
            fall-through boundary deterministically."""

            def random(self) -> float:
                return 1.0

        with pytest.raises(RuntimeError):
            machine.roll_move(owner, _MaxRoll())

    def test_all_zero_weight_branches_pick_the_first_branch_without_raising(self):
        a = _loop_move("A")
        b = _loop_move("B")
        branch = RandomBranchState("BR")
        # Both permanently disabled (step 21/G7 clause a: legal to BUILD,
        # each resolves to weight 0 at roll time) -- C# has no rule that a
        # branch set must keep at least one live option.
        branch.add_branch(a, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=0)
        branch.add_branch(b, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=0)
        machine = MonsterMoveStateMachine([a, b, branch], branch)
        owner = _Owner()
        owner.machine = machine
        rng = _CountingRandom(0)

        move = machine.roll_move(owner, rng)

        # RandomBranchState.cs:117-124: rng.NextFloat(0f) burns exactly ONE
        # draw and returns 0f; `num` starts at 0 and the FIRST branch added
        # wins immediately ("A", added before "B") -- no crash, no special
        # case, add-order is observable exactly as it is for a live roll.
        assert move.id == "A"
        assert rng.floats == 1

    def test_normal_weighted_roll_is_unaffected(self):
        # Regression guard: the common (non-degenerate) path still resolves
        # through the same loop with no behavior change.
        a = MoveState("A", lambda ctx: None, Intent(MoveType.ATTACK, damage=1))
        b = MoveState("B", lambda ctx: None, Intent(MoveType.ATTACK, damage=1))
        branch = RandomBranchState("BR")
        branch.add_branch(a, weight=1.0)
        branch.add_branch(b, weight=1.0)
        a.follow_up = branch
        b.follow_up = branch
        machine = MonsterMoveStateMachine([a, b, branch], branch)
        owner = _Owner()
        owner.machine = machine
        rng = random.Random(7)
        ids = set()
        for _ in range(200):
            move = machine.roll_move(owner, rng)
            machine.on_move_performed(move)
            ids.add(move.id)
        assert ids == {"A", "B"}


class TestUnreachableRegisteredState:
    """G2 (step 49): a state can be REGISTERED (present in `machine.states`,
    with real, live outgoing branches) without being WIRED reachable --
    mirroring PhrogParasite.cs:39-52's "RAND", which the game constructs,
    gives two real branches, and adds to the same list RegisterStates walks,
    then never points anything at."""

    @staticmethod
    def _phrog_shaped_machine():
        # INFECT <-> LASH FollowUp directly at each other
        # (PhrogParasite.cs:45-46); RAND has live CannotRepeat branches to
        # both but nothing ever transitions TO it.
        infect = MoveState("INFECT_MOVE", lambda ctx: None, Intent(MoveType.DEBUFF))
        lash = MoveState("LASH_MOVE", lambda ctx: None, Intent(MoveType.ATTACK, damage=5))
        infect.follow_up = lash
        lash.follow_up = infect
        rand = RandomBranchState("RAND")
        rand.add_branch(infect, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(lash, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        machine = MonsterMoveStateMachine(
            [infect, lash], infect, unreachable_states=(rand,))
        return machine, infect, lash, rand

    def test_unreachable_state_is_registered(self):
        machine, _infect, _lash, rand = self._phrog_shaped_machine()
        assert machine.states["RAND"] is rand

    def test_unreachable_state_is_never_rolled_and_draws_nothing(self):
        machine, infect, lash, _rand = self._phrog_shaped_machine()
        owner = _Owner()
        owner.machine = machine
        rng = _CountingRandom(0)
        machine._performed_first_move = True

        seq = [machine.current.id]
        for _ in range(6):
            move = machine.roll_move(owner, rng)
            machine.on_move_performed(move)
            seq.append(move.id)

        assert seq == ["INFECT_MOVE", "LASH_MOVE", "INFECT_MOVE", "LASH_MOVE",
                        "INFECT_MOVE", "LASH_MOVE", "INFECT_MOVE"]
        assert "RAND" not in seq
        assert rng.floats == 0

    def test_unreachable_state_still_rejects_a_duplicate_id(self):
        # Registration is the SAME call as the reachable list's
        # (`register_states`), so the duplicate-id guard (G8 clause a,
        # already fixed) applies uniformly regardless of which parameter a
        # state arrived through.
        infect = MoveState("INFECT_MOVE", lambda ctx: None, Intent(MoveType.DEBUFF))
        infect.follow_up = infect
        dup = RandomBranchState("INFECT_MOVE")  # id collides with `infect`
        with pytest.raises((ValueError, KeyError, RuntimeError)):
            MonsterMoveStateMachine([infect], infect, unreachable_states=(dup,))

    def test_omitting_unreachable_states_is_identical_to_before_this_parameter(self):
        move = _loop_move("ONLY")
        machine = MonsterMoveStateMachine([move], move)
        assert list(machine.states) == ["ONLY"]
