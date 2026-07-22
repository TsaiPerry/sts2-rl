"""Comparators + divergence report for the SP2 conformance runner.

The runner (runner.py) drives the parity-sim through a recording and, at each
room and floor boundary, compares the live sim against the save oracle. A
mismatch becomes a `Divergence` — the localized (stream, command_index,
expected vs. actual) pinpoint the SP2 spec promises. All helpers are pure so
they unit-test against constructed states.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..actmap import MapPointType
from ..rng import PlayerRngType, RunRngType

# The recording/save spell map-node types in lower-case words; the sim uses the
# MapPointType enum (ActModel node types). Fixed non-map rooms the save may name
# ("event") have no MapPointType and are simply not compared here.
NODE_TYPE_BY_NAME: dict[str, MapPointType] = {
    "unknown": MapPointType.UNKNOWN,
    "shop": MapPointType.SHOP,
    "treasure": MapPointType.TREASURE,
    "rest_site": MapPointType.REST_SITE,
    "monster": MapPointType.MONSTER,
    "elite": MapPointType.ELITE,
    "boss": MapPointType.BOSS,
    "ancient": MapPointType.ANCIENT,
}

# The four RNG streams SP2 makes parity-correct; combat streams stay on the
# legacy random.Random and are intentionally not compared (force-win stub).
SP2_RUN_STREAMS: tuple[RunRngType, ...] = (
    RunRngType.UP_FRONT,
    RunRngType.UNKNOWN_MAP_POINT,
)
SP2_PLAYER_STREAMS: tuple[PlayerRngType, ...] = (
    PlayerRngType.REWARDS,
    PlayerRngType.SHOPS,
)

# The seven RNG streams combat draws from (SP3). Diffed separately from the SP2
# run/player streams so a report says which subsystem diverged: a combat-stream
# mismatch means an un-ported combat draw, not a map/economy gap.
SP3_COMBAT_STREAMS: tuple[RunRngType, ...] = (
    RunRngType.SHUFFLE,
    RunRngType.MONSTER_AI,
    RunRngType.COMBAT_CARD_GENERATION,
    RunRngType.COMBAT_CARD_SELECTION,
    RunRngType.COMBAT_TARGETS,
    RunRngType.COMBAT_ENERGY_COSTS,
    RunRngType.COMBAT_POTION_GENERATION,
)


def node_type_name(t: MapPointType) -> str:
    """Reverse of NODE_TYPE_BY_NAME (falls back to the enum name)."""
    for name, mt in NODE_TYPE_BY_NAME.items():
        if mt == t:
            return name
    return t.name.lower()


@dataclass(frozen=True)
class Divergence:
    """One localized mismatch between the parity-sim and the save oracle."""

    stream: str          # a stream name, "map_point_type", or "runner"
    command_index: int   # recording room index (or -1 when floor-scoped)
    expected: object
    actual: object
    detail: str = ""

    def __str__(self) -> str:
        where = (
            f"room {self.command_index}" if self.command_index >= 0 else "floor end"
        )
        msg = (
            f"[{self.stream}] {where}: expected {self.expected!r}, "
            f"got {self.actual!r}"
        )
        return f"{msg} ({self.detail})" if self.detail else msg


def compare_node_type(
    room_index: int, recorded_type: str, sim_type: MapPointType
) -> Divergence | None:
    """The room the sim walked into should be the node type the save recorded.
    Recorded types with no MapPointType (e.g. a fixed "event" node) are skipped
    rather than flagged."""
    expected = NODE_TYPE_BY_NAME.get(recorded_type)
    if expected is None:
        return None
    if expected != sim_type:
        return Divergence(
            "map_point_type", room_index, recorded_type, node_type_name(sim_type)
        )
    return None


def compare_counters(
    run_counters: dict[RunRngType, int],
    player_counters: dict[PlayerRngType, int],
    oracle,
    run_streams: tuple[RunRngType, ...] = SP2_RUN_STREAMS,
    player_streams: tuple[PlayerRngType, ...] = SP2_PLAYER_STREAMS,
) -> list[Divergence]:
    """Diff the given RNG streams' counters against the save oracle. Returns a
    Divergence per mismatched stream (empty when all match)."""
    out: list[Divergence] = []
    for st in run_streams:
        exp, act = oracle.run_counters[st], run_counters[st]
        if exp != act:
            out.append(Divergence(st.value, -1, exp, act))
    for st in player_streams:
        exp, act = oracle.player_counters[st], player_counters[st]
        if exp != act:
            out.append(Divergence(st.value, -1, exp, act))
    return out
