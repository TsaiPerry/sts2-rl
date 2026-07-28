"""Task 7 (monster branch-table audit): move-sequence regression tests for
the hand-rolled overgrowth monsters `tools/audit_monster_machines.py` flags
as "hand-rolled but source has AddBranch calls".

Every monster tested here was traced by hand against its C# source
(`Slay the Spire 2/src/Core/Models/Monsters/*.cs`, `GenerateMoveStateMachine`)
and found to be ALREADY CORRECT -- no weight-vs-cooldown misread, no missing
MonsterAi draw. These tests exist to lock that verified-correct behaviour in
as a regression guard, in the same spirit as the TDD-first tests that caught
the real TwigSlimeM/Flyconid bugs (test_conformance_combat.py) -- the
difference is these ones were already green when written, because the audit
found no defect to fix.

Two of the four monsters below (Inklet, PhrogParasite) have a DEAD
RandomBranchState in their C# source: constructed and given branches, but
never wired into any MoveState.FollowUpState and never used as the machine's
initial state, so it is unreachable. Both monsters' real move graphs are a
plain MoveState->MoveState chain with a live RandomBranchState only at ONE
point in the cycle. The sim's hand-rolled code already matches the reachable
graph, not the dead one -- confirmed by the zero-draw assertions below.

The two classes at the BOTTOM of this file are a later addition and are not
part of that already-correct set: they pin `monster_state_machine/G1`, the
AddBranch-int-argument misread that five MachineMonster ports (FlailKnight,
HunterKiller, ScrollOfBiting, SpectralKnight, FakeMerchantMonster) did carry
and that was fixed against the C# overload table.
"""
from __future__ import annotations

import random
from types import SimpleNamespace

from sts2_rl.combat import CombatState
from sts2_rl.combat_rng import CombatRng
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.fake_merchant import FakeMerchantMonster
from sts2_rl.monsters.glory.knights import SpectralKnight
from sts2_rl.monsters.glory.scroll_of_biting import ScrollOfBiting
from sts2_rl.monsters.hive.flail_knight import FlailKnight, MysteriousKnight
from sts2_rl.monsters.hive.hunter_killer import HunterKiller
from sts2_rl.monsters.overgrowth.flyconid import FLYCONID_NORMAL, Flyconid
from sts2_rl.monsters.overgrowth.inklets import Inklet
from sts2_rl.monsters.overgrowth.phrog_parasite import PhrogParasite
from sts2_rl.monsters.overgrowth.slimes import SLIMES_NORMAL, TwigSlimeM
from sts2_rl.monsters.overgrowth.slithering_strangler import SlitheringStrangler
from sts2_rl.monsters.state_machine import MoveRepeatType, weighted_branch_pick
from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker
from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat
from sts2_rl.rng import GameRandomAdapter, RunRngSet


# Inklet.cs:73-74, the live `RAND` branch's arms in SOURCE ADD ORDER:
#   randomBranchState2.AddBranch(moveState3 /* PIERCING_GAZE_MOVE */, ...)
#   randomBranchState2.AddBranch(moveState2 /* WHIRLWIND_MOVE */, ...)
# Add order is observable even with equal weights: RandomBranchState.GetNextState
# subtracts the weights IN ADD ORDER and returns the first branch at num <= 0.
# This constant is transcribed from the C# source, never derived from the sim --
# an expectation computed from the code under test is not a pin.
_INKLET_RAND_ARMS = ["PIERCING_GAZE", "WHIRLWIND"]


class _FixedRoll:
    """Stands in for a move stream whose single RandomBranchState.GetNextState
    draw (`rng.NextFloat(total)`) is pinned to a known value, so which arm the
    weight walk lands on is a fact about the ADD ORDER alone."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


def _round(monster, ctx) -> None:
    """One enemy round for a lone monster: perform the telegraphed move, then
    take the intent roll.

    The roll used to sit at the bottom of each monster's `take_turn`. It does
    not belong there: `CombatManager.cs:478-484` rolls EVERY enemy's next move
    in one pass at the top of the PLAYER's turn
    (`foreach (Creature enemy in _state.Enemies) enemy.PrepareForNextTurn(...)`),
    which is `CombatState._roll_enemy_intents`. A test that drives a monster by
    hand has to make that pass itself. Every draw count and move sequence
    asserted below is a per-round fact and is unchanged by the move
    (turn_structure audit gap G9).
    """
    monster.take_turn(ctx)
    monster.telegraph_next_move()


def _single(monster_cls, seed: str, **kwargs) -> tuple[CombatState, object, RunRngSet]:
    enc = Encounter(id="test_" + monster_cls.__name__.lower(), monster_classes=[
        (lambda hooks, rng, cls=monster_cls: cls(hooks, rng, **kwargs))
    ])
    rs = RunRngSet(seed)
    combat = CombatState(rng_set=rs, encounter=enc)
    return combat, combat.enemies[0], rs


class TestInkletMoveSequence:
    """Inklet.cs: `INIT_RAND` RandomBranchState is built (AddBranch(moveState,
    2, 1f) / AddBranch(moveState2, CannotRepeat, 1f)) but never wired --
    `initialState` is JAB or WHIRLWIND directly. The live `RAND` state only
    sits between JAB and {WHIRLWIND, PIERCING_GAZE} (both CannotRepeat,
    weight 1 => a true 50/50 every time, since JAB is always the immediately
    preceding logged move when RAND is entered). WHIRLWIND/PIERCING_GAZE both
    FollowUp straight back to JAB_MOVE, bypassing RAND entirely -- no roll."""

    def test_jab_start_draws_nothing_at_construction(self):
        _, inklet, rs = _single(Inklet, "inklet-jab")
        assert inklet._move_key == "JAB"
        assert rs.monster_ai.counter == 0

    def test_middle_inklet_starts_whirlwind_no_draw(self):
        _, inklet, rs = _single(Inklet, "inklet-mid", is_middle=True)
        assert inklet._move_key == "WHIRLWIND"
        assert rs.monster_ai.counter == 0

    def test_whirlwind_returns_to_jab_with_no_roll(self):
        combat, inklet, rs = _single(Inklet, "inklet-mid2", is_middle=True)
        ctx = combat._ctx()
        _round(inklet, ctx)  # performs WHIRLWIND, follow-up is JAB directly
        assert inklet._move_key == "JAB"
        assert rs.monster_ai.counter == 0

    def test_jab_rolls_exactly_one_draw_matching_game_primitive(self):
        combat, inklet, rs = _single(Inklet, "inklet-roll")
        ctx = combat._ctx()

        # Independently compute what RAND (WHIRLWIND/PIERCING_GAZE, both
        # CannotRepeat weight 1) picks on a fresh stream at the same point:
        # nothing else has drawn from monster_ai yet (Inklet's own JAB start
        # and SlipperyPower application don't touch it).
        expected_rs = RunRngSet("inklet-roll")
        expected = weighted_branch_pick(
            GameRandomAdapter(expected_rs.monster_ai),
            _INKLET_RAND_ARMS, [1, 1],
        )

        _round(inklet, ctx)  # performs JAB, then rolls RAND
        assert inklet._move_key == expected
        assert rs.monster_ai.counter == 1

    def test_rand_arms_are_walked_in_the_c_sharp_add_order(self):
        """PIERCING_GAZE_MOVE is added FIRST (Inklet.cs:73), so a roll that
        lands in the first half of the [0, 2) weight span must resolve to
        PIERCING_GAZE and one in the second half to WHIRLWIND."""
        for value, expected in ((0.25, "PIERCING_GAZE"), (0.75, "WHIRLWIND")):
            combat, inklet, _ = _single(Inklet, "inklet-order")
            combat.combat_rng = CombatRng.legacy(_FixedRoll(value))
            assert inklet._move_key == "JAB"
            inklet.telegraph_next_move()  # the JAB -> RAND transition
            assert inklet._move_key == expected
        assert _INKLET_RAND_ARMS == ["PIERCING_GAZE", "WHIRLWIND"]

    def test_whirlwind_and_piercing_gaze_both_loop_to_jab_then_reroll(self):
        combat, inklet, rs = _single(Inklet, "inklet-cycle")
        ctx = combat._ctx()
        seq = [inklet._move_key]
        draws_before = rs.monster_ai.counter
        for _ in range(6):
            _round(inklet, ctx)
            seq.append(inklet._move_key)
        # Every JAB is immediately followed by a roll (WHIRLWIND or
        # PIERCING_GAZE); every WHIRLWIND/PIERCING_GAZE is immediately
        # followed by JAB with no roll. Total draws == number of JABs
        # actually performed (i.e. the number of JAB->X transitions).
        jabs_performed = seq[:-1].count("JAB")
        assert rs.monster_ai.counter - draws_before == jabs_performed
        for prev, nxt in zip(seq, seq[1:]):
            if prev == "JAB":
                assert nxt in ("WHIRLWIND", "PIERCING_GAZE")
            else:
                assert nxt == "JAB"


class TestPhrogParasiteMoveSequence:
    """PhrogParasite.cs: RAND RandomBranchState (2 CannotRepeat weight-1
    branches over INFECT/LASH) is built but never wired -- FollowUpState is
    set directly (INFECT<->LASH), and `initialState` is INFECT_MOVE. The
    alternation is fully deterministic; it must draw ZERO MonsterAi floats."""

    def test_starts_infect_no_draw(self):
        _, phrog, rs = _single(PhrogParasite, "phrog-1")
        assert phrog._move_key == "INFECT"
        assert rs.monster_ai.counter == 0

    def test_alternates_deterministically_with_zero_draws(self):
        combat, phrog, rs = _single(PhrogParasite, "phrog-2")
        ctx = combat._ctx()
        seq = [phrog._move_key]
        for _ in range(5):
            phrog.take_turn(ctx)
            seq.append(phrog._move_key)
        assert seq == ["INFECT", "LASH", "INFECT", "LASH", "INFECT", "LASH"]
        assert rs.monster_ai.counter == 0


class TestSlitheringStranglerMoveSequence:
    """SlitheringStrangler.cs: CONSTRICT's FollowUpState IS the live `rand`
    RandomBranchState (THWACK/LASH, both CanRepeatForever weight 1 -> an
    unconditional 50/50, one draw, every time). THWACK and LASH both
    FollowUp straight back to CONSTRICT with no roll."""

    def test_starts_constrict_no_draw(self):
        _, strangler, rs = _single(SlitheringStrangler, "strangler-1")
        assert strangler._move_key == "CONSTRICT"
        assert rs.monster_ai.counter == 0

    def test_constrict_rolls_one_draw_matching_game_primitive(self):
        combat, strangler, rs = _single(SlitheringStrangler, "strangler-2")
        ctx = combat._ctx()

        expected_rs = RunRngSet("strangler-2")
        expected = weighted_branch_pick(
            GameRandomAdapter(expected_rs.monster_ai), ["THWACK", "LASH"], [1, 1],
        )

        _round(strangler, ctx)  # performs CONSTRICT, then rolls rand
        assert strangler._move_key == expected
        assert rs.monster_ai.counter == 1

    def test_thwack_or_lash_returns_to_constrict_with_no_roll(self):
        combat, strangler, rs = _single(SlitheringStrangler, "strangler-3")
        ctx = combat._ctx()
        _round(strangler, ctx)
        after_roll = rs.monster_ai.counter
        assert strangler._move_key in ("THWACK", "LASH")
        _round(strangler, ctx)
        assert strangler._move_key == "CONSTRICT"
        assert rs.monster_ai.counter == after_roll

    def test_full_cycle_draw_count_equals_constrict_count(self):
        combat, strangler, rs = _single(SlitheringStrangler, "strangler-4")
        ctx = combat._ctx()
        seq = [strangler._move_key]
        for _ in range(7):
            _round(strangler, ctx)
            seq.append(strangler._move_key)
        constricts_performed = seq[:-1].count("CONSTRICT")
        assert rs.monster_ai.counter == constricts_performed
        for prev, nxt in zip(seq, seq[1:]):
            if prev == "CONSTRICT":
                assert nxt in ("THWACK", "LASH")
            else:
                assert nxt == "CONSTRICT"


class TestPreviouslyFixedBugClassRegression:
    """Flyconid and TwigSlimeM are the two monsters this bug class was
    originally attested in ([[monster-move-weight-vs-cooldown-bug]]) and
    were already fixed before this task. Both draw exactly once on EVERY
    transition (unlike Inklet/PhrogParasite/SlitheringStrangler, which have
    a deterministic leg with no branch state at all) -- a stronger guard
    against the "skip the roll when a branch is forced" variant of the bug."""

    def test_twig_slime_m_draws_every_turn(self):
        rs = RunRngSet("twig-regress")
        combat = CombatState(rng_set=rs, encounter=SLIMES_NORMAL)
        twig = next(e for e in combat.enemies if isinstance(e, TwigSlimeM))
        ctx = combat._ctx()
        # TwigSlimeM's own initial move is fixed (STICKY_SHOT, no roll); other
        # RAND monsters in this encounter (LeafSlimeS) may have already drawn
        # at combat-start telegraph, so snapshot the counter after construction.
        draws_before = rs.monster_ai.counter
        for i in range(5):
            _round(twig, ctx)
            assert rs.monster_ai.counter == draws_before + i + 1

    def test_flyconid_draws_every_turn(self):
        rs = RunRngSet("flyconid-regress")
        combat = CombatState(rng_set=rs, encounter=FLYCONID_NORMAL)
        fly = next(e for e in combat.enemies if isinstance(e, Flyconid))
        ctx = combat._ctx()
        draws_before = rs.monster_ai.counter
        for i in range(5):
            _round(fly, ctx)
            assert rs.monster_ai.counter == draws_before + i + 1


def _build_machine(cls, **fields):
    """Build a monster's machine without a combat (build_machine only reads
    ctor-set fields, which the caller supplies)."""
    obj = cls.__new__(cls)
    for k, v in fields.items():
        setattr(obj, k, v)
    return obj.build_machine()


def _branches_by_id(machine, branch_id: str) -> dict[str, dict]:
    return {b["state_id"]: b for b in machine.states[branch_id]._branches}


def _roll_ids(machine, seed: int, count: int) -> list[str]:
    """Walk the machine `count` transitions, returning the move-id sequence.
    Rolls the graph directly (no combat) so no move actually resolves."""
    owner = SimpleNamespace(machine=machine)
    rng = random.Random(seed)
    ids = [machine.current.id]
    for _ in range(count):
        machine.on_move_performed(machine.current)
        ids.append(machine.roll_move(owner, rng).id)
    return ids


def _max_run(ids: list[str], move_id: str) -> int:
    best = run = 0
    for got in ids:
        run = run + 1 if got == move_id else 0
        best = max(best, run)
    return best


class TestAddBranchIntArgsAreRepeatLimits:
    """`monster_state_machine/G1`. C#'s `RandomBranchState.AddBranch`
    (RandomBranchState.cs:46-113) never takes a weight in positional slot 2 --
    every one of its ten overloads puts a *cooldown* or a *maxRepeats* there
    and defaults the weight to 1f. Five ports transliterated the position and
    turned a repeat limit into a weight; these tests pin the overload
    resolution per call site, and the move sequences it produces."""

    def test_flail_knight_flail_and_ram_are_can_repeat_x_times_two(self):
        # FlailKnight.cs:50-51 `AddBranch(state, 2)` -> the (state, int
        # maxRepeats) overload (:71) -> maxTimes 2, CanRepeatXTimes, weight 1f.
        by_id = _branches_by_id(_build_machine(FlailKnight), "RAND")
        for move_id in ("FLAIL_MOVE", "RAM_MOVE"):
            b = by_id[move_id]
            assert b["weight"] == 1.0, move_id
            assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES, move_id
            assert b["max_times"] == 2, move_id
            assert b["cooldown"] == 0, move_id

    def test_flail_knight_never_picks_a_move_three_times_running(self):
        for seed in range(8):
            ids = _roll_ids(_build_machine(FlailKnight), seed, 300)
            assert _max_run(ids, "FLAIL_MOVE") <= 2, seed
            assert _max_run(ids, "RAM_MOVE") <= 2, seed
            assert _max_run(ids, "WAR_CHANT") <= 1, seed

    def test_mysterious_knight_inherits_the_flail_knight_machine(self):
        # MysteriousKnight.cs overrides only AfterAddedToRoom, so it inherits
        # FlailKnight.GenerateMoveStateMachine verbatim.
        assert MysteriousKnight.build_machine is FlailKnight.build_machine
        by_id = _branches_by_id(_build_machine(MysteriousKnight), "RAND")
        assert by_id["FLAIL_MOVE"]["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
        assert by_id["FLAIL_MOVE"]["max_times"] == 2
        assert by_id["RAM_MOVE"]["max_times"] == 2

    def test_hunter_killer_puncture_is_can_repeat_x_times_two(self):
        # HunterKiller.cs:43 `AddBranch(moveState3, 2)`.
        by_id = _branches_by_id(_build_machine(HunterKiller), "RAND")
        b = by_id["PUNCTURE_MOVE"]
        assert b["weight"] == 1.0
        assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
        assert b["max_times"] == 2
        assert b["cooldown"] == 0
        # HunterKiller.cs:42 is the (state, MoveRepeatType) overload: weight 1.
        assert by_id["BITE_MOVE"]["weight"] == 1.0
        assert by_id["BITE_MOVE"]["repeat_type"] is MoveRepeatType.CANNOT_REPEAT

    def test_hunter_killer_never_punctures_three_times_running(self):
        for seed in range(8):
            ids = _roll_ids(_build_machine(HunterKiller), seed, 300)
            assert _max_run(ids, "PUNCTURE_MOVE") <= 2, seed
            assert _max_run(ids, "BITE_MOVE") <= 1, seed

    def test_scroll_of_biting_chew_is_can_repeat_x_times_two(self):
        # ScrollOfBiting.cs:90 `AddBranch(moveState2, 2)`.
        machine = _build_machine(ScrollOfBiting, _starter_move_idx=0)
        by_id = _branches_by_id(machine, "rand")
        b = by_id["CHEW"]
        assert b["weight"] == 1.0
        assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
        assert b["max_times"] == 2
        assert b["cooldown"] == 0

    def test_scroll_of_biting_never_chews_three_times_running(self):
        for seed in range(8):
            machine = _build_machine(ScrollOfBiting, _starter_move_idx=1)
            ids = _roll_ids(machine, seed, 300)
            assert _max_run(ids, "CHEW") <= 2, seed

    def test_spectral_knight_soul_slash_is_can_repeat_x_times_two(self):
        # SpectralKnight.cs:52 `AddBranch(moveState2, 2)`.
        by_id = _branches_by_id(_build_machine(SpectralKnight), "RAND")
        b = by_id["SOUL_SLASH"]
        assert b["weight"] == 1.0
        assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
        assert b["max_times"] == 2
        assert b["cooldown"] == 0

    def test_spectral_knight_never_soul_slashes_three_times_running(self):
        for seed in range(8):
            ids = _roll_ids(_build_machine(SpectralKnight), seed, 300)
            assert _max_run(ids, "SOUL_SLASH") <= 2, seed
            assert _max_run(ids, "SOUL_FLAME") <= 1, seed

    def test_fake_merchant_enrage_is_a_cooldown_of_three(self):
        # FakeMerchantMonster.cs:58 `AddBranch(moveState4, 3, CannotRepeat)`
        # -> the (state, int cooldown, MoveRepeatType) overload (:95): cooldown
        # 3, CannotRepeat, weight 1f -- NOT weight 3.
        by_id = _branches_by_id(_build_machine(FakeMerchantMonster), "RAND_MOVE")
        b = by_id["ENRAGE_MOVE"]
        assert b["weight"] == 1.0
        assert b["repeat_type"] is MoveRepeatType.CANNOT_REPEAT
        assert b["max_times"] == 0
        assert b["cooldown"] == 3

    def test_fake_merchant_enrages_at_most_once_every_four_moves(self):
        for seed in range(8):
            ids = _roll_ids(_build_machine(FakeMerchantMonster), seed, 300)
            hits = [i for i, got in enumerate(ids) if got == "ENRAGE_MOVE"]
            assert hits, seed  # it must still be reachable
            for prev, nxt in zip(hits, hits[1:]):
                assert nxt - prev >= 4, (seed, prev, nxt)


class TestAddBranchIntArgsAlreadyCorrect:
    """The two ports the audit found reading the same argument shapes
    CORRECTLY; pinned so the G1 sweep cannot regress them."""

    def test_fossil_stalker_branches_are_can_repeat_x_times_two(self):
        # FossilStalker.cs:58-60 `AddBranch(state, 2)` x3.
        by_id = _branches_by_id(_build_machine(FossilStalker), "RAND")
        for b in by_id.values():
            assert b["weight"] == 1.0
            assert b["repeat_type"] is MoveRepeatType.CAN_REPEAT_X_TIMES
            assert b["max_times"] == 2
            assert b["cooldown"] == 0

    def test_two_tailed_rat_screech_is_a_cooldown_of_three(self):
        # TwoTailedRat.cs:127 `AddBranch(moveState3, 3, CannotRepeat, lambda)`.
        machine = _build_machine(TwoTailedRat, _starter_move_idx=-1)
        by_id = _branches_by_id(machine, "RAND")
        b = by_id["SCREECH_MOVE"]
        assert b["repeat_type"] is MoveRepeatType.CANNOT_REPEAT
        assert b["max_times"] == 0
        assert b["cooldown"] == 3
