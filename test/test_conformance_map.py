"""SP2 Task 7: act-map layout parity against the recordings.

The run.save serializes the *sequence of map-point types the player walked*
(``map_point_history[act]``) but not per-node coordinates, so the strongest
oracle the save supports is structural: the map the sim carves from the
parity ``act_N_map`` stream must contain, at each row the player passed
through, a node of the recorded type. (A bit-exact per-node check would need
a map grid dumped from sts2.dll — a follow-up.)

Act 1 is checked here because its map is generated with zero relics/cards in
play (Neow fires after the first act's map is built), so its layout is a
clean function of the seed alone. Later acts can carry map-editing relics and
denser type counts, so their exact verification is deferred to the
dll-dumped grid oracle. See
docs/superpowers/specs/2026-07-20-sp2-map-economy-parity-design.md."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sts2_rl.actmap import MapPointType
from sts2_rl.run import RunState

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays saves not present")

# Save act id -> ActMapConfig name (Overgrowth and Underdocks share a config).
_ACT_CONFIG = {
    "ACT.OVERGROWTH": "overgrowth",
    "ACT.UNDERDOCKS": "underdocks",
    "ACT.HIVE": "hive",
    "ACT.GLORY": "glory",
}
_TYPE_NAME = {t: t.name.lower() for t in MapPointType}


def _load_save(seed: str, floor: str = "floor_18") -> dict:
    return json.loads(
        (REC / seed / floor / "run.save").read_text(encoding="utf-8-sig")
    )


def _rows_by_index(act_map) -> dict[int, set[str]]:
    rows: dict[int, set[str]] = {}
    for point in act_map.all_points():
        rows.setdefault(point.row, set()).add(_TYPE_NAME[point.point_type])
    return rows


def _act1_map(seed: str, save: dict):
    act_id = save["acts"][0]["id"]
    run = RunState(string_seed=seed)
    return run.start_act(
        _ACT_CONFIG[act_id],
        ascension=save.get("ascension", 0),
        is_final_act=False,
        act_index=0,
    )


@pytest.mark.parametrize("seed", sorted(p.name for p in REC.iterdir()))
def test_act1_map_layout_matches_recording(seed: str):
    save = _load_save(seed)
    oracle = [p["map_point_type"] for p in save["map_point_history"][0]]
    act_map = _act1_map(seed, save)
    rows = _rows_by_index(act_map)
    # rows 0 (ancient) and last (boss) are structural; check the interior rows
    # the player actually walked (one node per row in the history).
    missing = [
        (r, oracle[r]) for r in range(1, len(oracle) - 1)
        if oracle[r] not in rows.get(r, set())
    ]
    assert not missing, f"{seed} act1 rows without the recorded type: {missing}"


def test_act1_map_oracle_discriminates():
    # Guard against the structural check being trivially satisfied: a map
    # carved from a different seed should NOT reproduce this seed's full
    # per-row type sequence.
    save = _load_save("89U21BV1TZ")
    oracle = [p["map_point_type"] for p in save["map_point_history"][0]]
    other = RunState(string_seed="DJDCSAQZNR").start_act(
        "overgrowth", ascension=1, is_final_act=False, act_index=0
    )
    rows = _rows_by_index(other)
    matches = sum(
        1 for r in range(1, len(oracle) - 1) if oracle[r] in rows.get(r, set())
    )
    assert matches < len(oracle) - 2
