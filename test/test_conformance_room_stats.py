"""DETECTOR 5: per-room player-state oracle from map_point_history."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.save import parse_save

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")


def test_room_stats_parsed_per_act():
    o = parse_save(REC / "933T39V18D" / "floor_49" / "run.save")
    assert [len(a) for a in o.room_stats_by_act] == [17, 16, 15]
    st = o.room_stats_by_act[1][3]          # act 1, 4th point — known values
    assert st.current_hp == 69
    assert st.max_hp == 80
    assert st.damage_taken == 17
    assert st.hp_healed == 6
    assert st.current_gold == 345
    # every parsed point carries a map_point_type string
    assert all(p.map_point_type for act in o.room_stats_by_act for p in act)


def test_room_stats_empty_when_history_absent():
    # floor_18 truncation saves still carry history; construct absence instead
    from sts2_rl.conformance.save import SaveOracle
    o = SaveOracle(run_seed="X", player_seed=0, ascension=0, acts=[],
                   current_act_index=0, run_counters={}, player_counters={})
    assert o.room_stats_by_act == []


def test_detector5_reports_room_hp_divergence_for_933t():
    """With check_room_stats=True the runner emits room_* divergences wherever
    the sim's post-room state differs from map_point_history. This is
    report-only — divergence lists elsewhere (player_hp, floor_*) are
    unchanged, and running with the flag off emits none."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner

    b = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    on = ReplayRunner(rec, oracle).run(stop_after_act=2, check_room_stats=True)
    off = ReplayRunner(parse_recording(b / "actions.sts2replay"),
                       parse_save(b / "run.save")).run(stop_after_act=2)
    room = [d for d in on.divergences if d.stream.startswith("room_")]
    assert not [d for d in off.divergences if d.stream.startswith("room_")]
    # the flag must not perturb the replay itself
    assert on.forced_combats == off.forced_combats
    # each room divergence is localized: detail names act/room/point-type
    # (the brief's interface note called this field "note"; the actual
    # Divergence dataclass in comparators.py names it "detail" — this test
    # was adjusted to match the real field name rather than the brief's text)
    for d in room:
        assert "act " in d.detail and "room " in d.detail


def test_room_stats_reachability_guard_reports_when_sim_also_disagrees():
    """Code review Important fix (2026-08-04): the reachability guard used
    to skip ANY history point unreachable from the previous point,
    regardless of what the live sim did — sim-blind, same defect class as
    the floor-save exclusion. Narrowed: skip ONLY when the point is
    unreachable from `prev` AND the live sim's hp equals `prev.current_hp`
    (history is PROVABLY the liar there). If the sim ALSO disagrees with
    `prev`, this is not provably a capture artifact — record the
    divergence rather than silently swallow it.

    Unit-level, no fixtures required: constructs a bare two-point
    `room_stats_by_act` via `ReplayRunner.__new__` and calls
    `_check_room_stats` directly with a `SimpleNamespace` stand-in for
    `run`, so both branches are exercised deterministically."""
    from types import SimpleNamespace

    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import RoomStats, SaveOracle

    prev = RoomStats(map_point_type="rest", current_hp=70, max_hp=80,
                      damage_taken=0, hp_healed=0, current_gold=0,
                      gold_gained=0, gold_spent=0, gold_lost=0,
                      gold_stolen=0, max_hp_gained=0, max_hp_lost=0)
    # cur: arith = 40 + 10 - 0 = 50 != prev.current_hp (70) -> unreachable.
    cur = RoomStats(map_point_type="combat", current_hp=40, max_hp=80,
                     damage_taken=10, hp_healed=0, current_gold=0,
                     gold_gained=0, gold_spent=0, gold_lost=0,
                     gold_stolen=0, max_hp_gained=0, max_hp_lost=0)

    runner = ReplayRunner.__new__(ReplayRunner)
    runner.oracle = SaveOracle(
        run_seed="x", player_seed=0, ascension=0, acts=[],
        current_act_index=0, run_counters={}, player_counters={},
        room_stats_by_act=[[prev, cur]])

    # Sim ALSO disagrees with the one reachable reference (70) -> must
    # report the room_hp divergence, not silently skip it.
    divergences = []
    run_disagrees = SimpleNamespace(hp=999, max_hp=80, gold=0, total_floor=2)
    runner._check_room_stats(run_disagrees, divergences, 0, 1)
    assert any(d.stream == "room_hp" for d in divergences)

    # Sim agrees with the reachable reference (70) -> history is provably
    # the liar; skip (report-only, no real divergence to flag).
    divergences2 = []
    run_agrees = SimpleNamespace(hp=70, max_hp=80, gold=0, total_floor=2)
    runner._check_room_stats(run_agrees, divergences2, 0, 1)
    assert divergences2 == []


@pytest.mark.skipif(
    not all((REC / seed / "floor_49" / "run.save").exists()
            for seed in ("933T39V18D", "89U21BV1TZ")),
    reason="per-seed floor_49 fixtures not present")
def test_detector5_skips_the_zeroed_terminal_boss_point():
    """The final act-2 room in `map_point_history` (the boss point) captures
    an internally-inconsistent all-zero `player_stats` block
    (current_hp=max_hp=current_gold=0) in BOTH installed recordings
    (89U21BV1TZ and 933T39V18D) — a run-end capture artifact, not a real 0
    HP/gold moment (the sim, and the run-end save's own top-level `players[0]`
    block, both show the player alive with real HP at the boss). Task 3
    (oracle_semantics_probe decision table) resolves this by having
    `_check_room_stats` skip any point whose stats are internally
    inconsistent — unreachable from the previous point via
    `current_hp + damage_taken - hp_healed` — rather than reporting a
    phantom `room_hp`/`room_max_hp`/`room_gold` divergence for it every run."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner

    for seed in ("933T39V18D", "89U21BV1TZ"):
        b = REC / seed / "floor_49"
        rec = parse_recording(b / "actions.sts2replay")
        oracle = parse_save(b / "run.save")
        # Sanity: the fixture really is the zeroed-terminal-point case this
        # test guards against.
        boss = oracle.room_stats_by_act[2][-1]
        assert (boss.current_hp, boss.max_hp, boss.current_gold) == (0, 0, 0)

        result = ReplayRunner(rec, oracle).run(
            stop_after_act=2, check_room_stats=True)
        terminal_divs = [
            d for d in result.divergences
            if d.stream.startswith("room_") and "room 14" in d.detail
        ]
        assert terminal_divs == [], (seed, terminal_divs)
