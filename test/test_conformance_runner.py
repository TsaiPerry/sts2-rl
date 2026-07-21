"""SP2 Task 10: the conformance runner replays a recording through the
parity-sim with a force-win combat stub and diffs the walk + RNG counters.

Scope note: Task 10 lands before the economy streams are wired (Task 9), so
the runner verifies what is live now — the exact map walk (every
``MoveToMapCoord`` lands on the recorded node type) and the ``UpFront`` counter
(413 at the act-1 boss). The ``UnknownMapPoint`` / ``Rewards`` / ``Shops``
counters still read 0 (they draw on the legacy RNG until Task 9); the runner
reports them as pending divergences, asserted here so the expected-state is
explicit and flips to a hard match once Task 9 wires the economy streams."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.rng import PlayerRngType, RunRngType

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

SEED = "89U21BV1TZ"  # floor_18 = act 1 only (no Hive act-2 map divergence)

# Streams whose counters are wired to the parity RNG today (pre-Task-9).
_WIRED = frozenset({RunRngType.UP_FRONT})
# Streams Task 9 still has to route onto the parity RNG.
_PENDING_LABELS = frozenset(
    {RunRngType.UNKNOWN_MAP_POINT.value,
     PlayerRngType.REWARDS.value, PlayerRngType.SHOPS.value}
)


def _run(seed: str, floor: str = "floor_18"):
    base = REC / seed / floor
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    return ReplayRunner(rec, oracle).run(stop_after_act=0), oracle


def test_runner_reproduces_act1_walk():
    result, oracle = _run(SEED)
    # Every MoveToMapCoord landed on a travelable node of the recorded type,
    # all the way to the act-1 boss — no map or navigation divergence.
    assert result.reached_act_end, result.stopped_reason
    assert result.rooms_walked == len(oracle.map_history[0]) - 1  # minus Neow
    map_or_nav = [d for d in result.divergences
                  if d.stream in ("map_point_type", "runner")]
    assert not map_or_nav, map_or_nav


def test_runner_matches_upfront_counter():
    result, oracle = _run(SEED)
    # UpFront is fully wired (8f): room generation lands it at the save value
    # and the force-win walk adds no in-run UpFront draws for this seed.
    assert result.run_counters[RunRngType.UP_FRONT] == \
        oracle.run_counters[RunRngType.UP_FRONT] == 413
    assert not any(
        d.stream == RunRngType.UP_FRONT.value for d in result.divergences)


def test_runner_economy_streams_pending_task9():
    """Until Task 9 routes them onto the parity RNG, the economy streams read
    0 and are the *only* remaining divergences. This test documents that state
    and must be tightened (to a hard counter match) when Task 9 lands."""
    result, _ = _run(SEED)
    pending = {d.stream for d in result.divergences}
    assert pending == _PENDING_LABELS, result.divergences
    assert result.run_counters[RunRngType.UNKNOWN_MAP_POINT] == 0
    assert result.player_counters[PlayerRngType.REWARDS] == 0
    assert result.player_counters[PlayerRngType.SHOPS] == 0
