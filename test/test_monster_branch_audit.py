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
"""
from __future__ import annotations

from sts2_rl.combat import CombatState
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.flyconid import FLYCONID_NORMAL, Flyconid
from sts2_rl.monsters.overgrowth.inklets import Inklet
from sts2_rl.monsters.overgrowth.phrog_parasite import PhrogParasite
from sts2_rl.monsters.overgrowth.slimes import SLIMES_NORMAL, TwigSlimeM
from sts2_rl.monsters.overgrowth.slithering_strangler import SlitheringStrangler
from sts2_rl.monsters.state_machine import weighted_branch_pick
from sts2_rl.rng import GameRandomAdapter, RunRngSet


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
        inklet.take_turn(ctx)  # performs WHIRLWIND, follow-up is JAB directly
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
            ["WHIRLWIND", "PIERCING_GAZE"], [1, 1],
        )

        inklet.take_turn(ctx)  # performs JAB, then rolls RAND
        assert inklet._move_key == expected
        assert rs.monster_ai.counter == 1

    def test_whirlwind_and_piercing_gaze_both_loop_to_jab_then_reroll(self):
        combat, inklet, rs = _single(Inklet, "inklet-cycle")
        ctx = combat._ctx()
        seq = [inklet._move_key]
        draws_before = rs.monster_ai.counter
        for _ in range(6):
            inklet.take_turn(ctx)
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

        strangler.take_turn(ctx)  # performs CONSTRICT, then rolls rand
        assert strangler._move_key == expected
        assert rs.monster_ai.counter == 1

    def test_thwack_or_lash_returns_to_constrict_with_no_roll(self):
        combat, strangler, rs = _single(SlitheringStrangler, "strangler-3")
        ctx = combat._ctx()
        strangler.take_turn(ctx)
        after_roll = rs.monster_ai.counter
        assert strangler._move_key in ("THWACK", "LASH")
        strangler.take_turn(ctx)
        assert strangler._move_key == "CONSTRICT"
        assert rs.monster_ai.counter == after_roll

    def test_full_cycle_draw_count_equals_constrict_count(self):
        combat, strangler, rs = _single(SlitheringStrangler, "strangler-4")
        ctx = combat._ctx()
        seq = [strangler._move_key]
        for _ in range(7):
            strangler.take_turn(ctx)
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
            twig.take_turn(ctx)
            assert rs.monster_ai.counter == draws_before + i + 1

    def test_flyconid_draws_every_turn(self):
        rs = RunRngSet("flyconid-regress")
        combat = CombatState(rng_set=rs, encounter=FLYCONID_NORMAL)
        fly = next(e for e in combat.enemies if isinstance(e, Flyconid))
        ctx = combat._ctx()
        draws_before = rs.monster_ai.counter
        for i in range(5):
            fly.take_turn(ctx)
            assert rs.monster_ai.counter == draws_before + i + 1
