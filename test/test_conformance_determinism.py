"""Two identical ReplayRunner passes must produce identical results — the
conformance shared rng is seeded (runner.py), so triage deltas are real."""
from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"


@pytest.mark.skipif(not REC.exists(), reason="RunReplays fixtures not present")
def test_replay_runner_is_deterministic():
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "89U21BV1TZ" / "floor_18"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    r1 = ReplayRunner(rec, oracle).run(stop_after_act=0)
    r2 = ReplayRunner(rec, oracle).run(stop_after_act=0)
    assert [repr(d) for d in r1.divergences] == [repr(d) for d in r2.divergences]
    assert [repr(d) for d in r1.combat_divergences] == [repr(d) for d in r2.combat_divergences]
    assert r1.run_counters == r2.run_counters
    assert r1.forced_combats == r2.forced_combats
