"""Parse a RunReplays run.save (clean JSON) into a SaveOracle (SP2 harness).

We read only the fields the conformance harness needs: the rng block
(``/rng`` — the 12 RunRngSet stream counters + string seed — and
``/players[0]/rng`` — the 3 PlayerRngSet counters + numeric seed), plus the
per-act pre-rolled encounter id lists and map history used as parity oracles.
No full save deserialization. See
docs/superpowers/specs/2026-07-20-sp2-map-economy-parity-design.md."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sts2_rl.rng import RunRngType, PlayerRngType, snake_case


@dataclass
class SaveOracle:
    run_seed: str
    player_seed: int
    ascension: int
    acts: list[str]
    current_act_index: int
    run_counters: dict[RunRngType, int]
    player_counters: dict[PlayerRngType, int]
    encounter_ids_by_act: list[dict[str, list[str]]]
    visited_coords: list = field(default_factory=list)
    map_history: list = field(default_factory=list)


def parse_save(path) -> SaveOracle:
    d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    run_counters = {
        t: d["rng"]["counters"][snake_case(t.value)] for t in RunRngType
    }
    prng = d["players"][0]["rng"]
    player_counters = {
        t: prng["counters"][snake_case(t.value)] for t in PlayerRngType
    }
    encs: list[dict[str, list[str]]] = []
    for act in d.get("acts", []):
        rooms = act.get("rooms", {})
        encs.append({
            "normal": rooms.get("normal_encounter_ids", []),
            "elite": rooms.get("elite_encounter_ids", []),
            "event": rooms.get("event_ids", []),
            "boss": rooms.get("boss_id"),
            "ancient": rooms.get("ancient_id"),
            "second_boss": rooms.get("second_boss_id"),
        })
    return SaveOracle(
        run_seed=d["rng"]["seed"],
        player_seed=prng["seed"],
        ascension=d.get("ascension", 0),
        acts=[a.get("id") for a in d.get("acts", [])],
        current_act_index=d.get("current_act_index", 0),
        run_counters=run_counters,
        player_counters=player_counters,
        encounter_ids_by_act=encs,
        visited_coords=d.get("visited_map_coords", []),
        map_history=d.get("map_point_history", []),
    )
