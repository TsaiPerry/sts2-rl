"""SP2 Task 10: the conformance runner replays a recording through the
parity-sim with a force-win combat stub and diffs the walk + RNG counters.

Task 9 wired the four SP2 RNG streams onto the parity RNG:
  - ``UpFront`` — run/room generation (8f), 413 at the act-1 boss.
  - ``UnknownMapPoint`` — "?"-node resolution (RunOddsSet), 3.
  - ``Rewards`` — combat/treasure reward generation (gold, potion pity+drop,
    cards, elite relic rarity), 141.
  - ``Shops`` — merchant generation (on-sale index, card/potion picks, cost
    jitter), 56. (Merchant card/relic rarity + upgrade rolls draw on the
    *Rewards* stream, as in the source.)

The full act-1 walk of 89U21BV1TZ (Ironclad) reproduces all four counters
exactly with zero divergences.

Cross-seed note: ``Shops`` / ``UnknownMapPoint`` / ``UpFront`` match all five
RunReplays recordings; ``Rewards`` matches every seed whose act-1 events award
nothing on the reward stream. Two seeds (DJDCSAQZNR, QRWCVDPZN5) walk through
events (brain_leech, self_help_book, …) whose per-event reward-draw counts the
Ironclad-only sim doesn't yet reproduce — an event-fidelity gap distinct from
the reward/shop wiring, tracked separately."""
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

# Every SP2 stream + its expected floor-18 counter for the Ironclad seed.
_EXPECTED_RUN = {RunRngType.UP_FRONT: 413, RunRngType.UNKNOWN_MAP_POINT: 3}
_EXPECTED_PLAYER = {PlayerRngType.REWARDS: 141, PlayerRngType.SHOPS: 56}


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


def test_runner_matches_run_counters():
    result, oracle = _run(SEED)
    # UpFront (room generation) and UnknownMapPoint ("?"-node resolution) both
    # land at the save value with no in-run divergence.
    for stream, expected in _EXPECTED_RUN.items():
        assert result.run_counters[stream] == oracle.run_counters[stream] == expected


def test_runner_matches_economy_counters():
    result, oracle = _run(SEED)
    # Rewards (combat/treasure reward generation) and Shops (merchant
    # generation) reproduce the save counters exactly.
    for stream, expected in _EXPECTED_PLAYER.items():
        assert result.player_counters[stream] == \
            oracle.player_counters[stream] == expected


def test_runner_has_no_divergences():
    result, _ = _run(SEED)
    # All four SP2 streams + the whole map/room-type walk agree with the save.
    assert result.ok, [str(d) for d in result.divergences]
