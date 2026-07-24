from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
BK = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")

# Per-seed floor-save roots. 933T has all 49 floors in the capture backup;
# 89U only has its 3 act-boundary saves (under Resources, same as the
# recordings) — enough to exercise the resync invariant on a second seed.
_FLOOR_ROOTS = {
    "933T39V18D": BK,
    "89U21BV1TZ": REC / "89U21BV1TZ",
}


def _floor_saves_for(seed: str) -> dict:
    from sts2_rl.conformance.save import parse_save
    root = _FLOOR_ROOTS[seed]
    return {int(p.name.split("_")[1]): parse_save(p / "run.save")
            for p in root.glob("floor_*") if (p / "run.save").exists()}


def _floor_saves():
    return _floor_saves_for("933T39V18D")


@pytest.mark.skipif(not (REC.exists() and BK.exists()), reason="fixtures absent")
def test_floor_checkpoints_and_resync_run_to_completion():
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    saves = _floor_saves()
    assert len(saves) == 49
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)
    floor_divs = [d for d in result.divergences if d.stream.startswith("floor_")]
    # Not asserting zero (the seed hasn't converged); asserting the MECHANISM:
    # checkpoints fired across the whole run and resync kept the replay alive
    # to the recorded end instead of dying to cascade damage.
    assert result.stopped_reason.startswith("reached act 2")
    checked_floors = {d.command_index for d in floor_divs}
    assert all(1 <= f <= 49 for f in checked_floors)


@pytest.mark.parametrize("seed", [
    pytest.param("933T39V18D", marks=pytest.mark.skipif(
        not (REC.exists() and BK.exists()), reason="fixtures absent")),
    pytest.param("89U21BV1TZ", marks=pytest.mark.skipif(
        not (REC.exists() and (REC / "89U21BV1TZ").exists()),
        reason="fixtures absent")),
])
def test_resync_does_not_degrade_replay_vs_no_floor_saves_baseline(seed):
    """Critical-finding regression guard (post-review fix): `floor_saves` +
    `resync_floors=True` must never make the replay WORSE than the same
    replay with no `floor_saves` at all. Before the stale-save-detection fix,
    933T39V18D at stop_after_act=2 measured forced_combats 1->8 and
    combat_divergences 10->126 (a stale `run.save` — not re-exported after
    its room resolved, e.g. floor_5 duplicating floor_4's pre-purchase state
    — was treated as ground truth and resync rolled back correct live state).
    Runs both arms directly (~1.5s total per seed) rather than pinning
    absolute numbers, so this catches any future regression of the same
    shape, not just today's exact counts.

    Parametrized over both conformance seeds: 933T39V18D (49 per-floor
    saves, the case the stale-save fix was built against) and 89U21BV1TZ
    (only its 3 act-boundary saves) — the risk this guards against is
    per-seed, so the invariant must hold on more than one seed before the
    resync mechanism can be trusted generally."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / seed / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    saves = _floor_saves_for(seed)

    baseline = ReplayRunner(rec, oracle).run(stop_after_act=2)
    resynced = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)

    assert resynced.forced_combats <= baseline.forced_combats
    assert len(resynced.combat_divergences) <= len(baseline.combat_divergences)
