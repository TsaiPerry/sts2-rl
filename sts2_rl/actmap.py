"""Act map generation — a faithful port of the game's map pipeline.

Mirrors src/Core/Map in the decompiled source:
  - StandardActMap.cs   → StandardMap (path carving + point-type assignment)
  - MapPoint.cs         → MapPoint
  - MapPointType.cs     → MapPointType (same enum values; they feed the
                          pruning segment keys)
  - MapPointTypeCounts.cs → MapPointTypeCounts + standard_unknown_count
  - MapPathPruning.cs   → prune_and_repair / find_matching_segments
  - MapPostProcessing.cs → center_grid / spread_adjacent_points /
                          straighten_paths
  - GoldenPathActMap.cs → golden_path_map (fixed single-column map)

The generator is act-agnostic: every act supplies its grid height and its
point-type-count rolls through an `ActMapConfig` (mirroring ActModel's
BaseNumberOfRooms / GetMapPointTypes). Configs for all four acts are
transcribed from the source (Overgrowth/Underdocks/Hive/Glory.cs), so Acts
2-3 maps generate correctly today even though their run layers (events,
shops) aren't in the sim yet.

Pipeline (StandardActMap constructor order):
  1. carve 7 bottom-to-top random-walk paths on a 7-wide grid, sharing
     nodes (the DAG), rejecting X crossovers;
  2. assign point types: forced rows (row 1 = Monster, rows-7 = Treasure,
     top row = RestSite), then a queue of rests/shops/elites/unknowns
     placed under the legality rules, leftovers become Monster;
  3. prune duplicate path segments (two routes offering the identical
     room-type sequence between the same junctions) and repair any type
     counts the pruning knocked below target;
  4. cosmetic post-processing (center / spread / straighten) that moves
     nodes between columns without touching topology.

The two ascension levels that touch map generation are modeled: pass an
`ascension` level (see AscensionLevel) for SwarmingElites (Asc 1+, 8 elites)
and `has_second_boss=True` for DoubleBoss (Asc 10, final act). The other
nine levels change combat/economy, not the map.

Deliberate deviations from the source (documented per the repo convention):
  - one shared `random.Random` instead of the game's seeded "act_N_map"
    Rng stream — no seed parity with the real game, but deterministic
    under the sim's own seeds;
  - no multiplayer node removal; the Warden treasure→elite swap is exposed
    as `replace_treasure_with_elites` but defaults off (it has no live
    ascension trigger in the source);
  - no run-level hooks (free travel, map-editing quests/relics).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Callable, Iterable, Iterator


class AscensionLevel(IntEnum):
    """AscensionLevel.cs — cumulative thresholds.

    A run at level N has every effect from 1..N (AscensionManager.HasLevel
    is `level >= threshold`, max 10). Only two levels touch map generation:
    SwarmingElites (8 elites instead of 5) and DoubleBoss (a second boss on
    the final act). The rest change combat/economy, not the map.
    """

    NONE = 0
    SWARMING_ELITES = 1
    WEARY_TRAVELER = 2
    POVERTY = 3
    TIGHT_BELT = 4
    ASCENDERS_BANE = 5
    INFLATION = 6
    SCARCITY = 7
    TOUGH_ENEMIES = 8
    DEADLY_ENEMIES = 9
    DOUBLE_BOSS = 10


# StandardActMap / MapPointTypeCounts elite counts (non-ascension = 5).
_BASE_ELITE_COUNT = 5
_SWARMING_ELITE_COUNT = round(_BASE_ELITE_COUNT * 1.6)  # 8


class MapPointType(IntEnum):
    """MapPointType.cs — values matter (pruning keys use the ints)."""

    UNASSIGNED = 0
    UNKNOWN = 1
    SHOP = 2
    TREASURE = 3
    REST_SITE = 4
    MONSTER = 5
    ELITE = 6
    BOSS = 7
    ANCIENT = 8


class _OrderedSet:
    """A minimal insertion-ordered set (dict-backed) that still compares equal
    to plain sets. MapPoint.children uses it so FindAllPaths enumerates
    children in link order — matching the game's HashSet iteration (insertion
    order, as generation only ever adds children), which drives
    duplicate-segment pruning — while every existing set-style use (``in``,
    ``len``, iteration, ``== {..}``) keeps working unchanged."""

    __slots__ = ("_d",)

    def __init__(self, iterable=()) -> None:
        self._d = dict.fromkeys(iterable)

    def add(self, item) -> None:
        self._d[item] = None

    def discard(self, item) -> None:
        self._d.pop(item, None)

    def __contains__(self, item) -> bool:
        return item in self._d

    def __iter__(self):
        return iter(self._d)

    def __len__(self) -> int:
        return len(self._d)

    def __eq__(self, other) -> bool:
        if isinstance(other, _OrderedSet):
            return self._d.keys() == other._d.keys()
        if isinstance(other, (set, frozenset)):
            return set(self._d) == other
        return NotImplemented

    __hash__ = None

    def __repr__(self) -> str:
        return "{" + ", ".join(repr(k) for k in self._d) + "}"


class MapPoint:
    """A node on the act map (MapPoint.cs).

    Identity semantics (like the C# class): two MapPoints are the same
    node only if they are the same object. Coordinates are unique per map,
    so identity and coord-equality coincide in practice.
    """

    def __init__(self, col: int, row: int) -> None:
        self.col = col
        self.row = row
        self.parents: set[MapPoint] = set()
        # Insertion-ordered so FindAllPaths matches the game's child iteration
        # (see _OrderedSet / _find_all_paths).
        self.children: _OrderedSet = _OrderedSet()
        self.point_type = MapPointType.UNASSIGNED
        # StandardActMap.AssignPointTypes marks forced rows immutable so
        # later systems (repair, map-editing effects) leave them alone.
        self.can_be_modified = True
        # Models attached to this point (MapPoint.Quests). The Spoils Map
        # card attaches itself to the treasure node so entering it pays out
        # (AddQuest / RemoveQuest in the source).
        self.quests: list = []

    @property
    def coord(self) -> tuple[int, int]:
        return (self.col, self.row)

    def add_quest(self, model) -> None:
        """MapPoint.AddQuest."""
        if model not in self.quests:
            self.quests.append(model)

    def remove_quest(self, model) -> None:
        """MapPoint.RemoveQuest."""
        if model in self.quests:
            self.quests.remove(model)

    def add_child(self, child: MapPoint) -> None:
        self.children.add(child)
        child.parents.add(self)

    def remove_child(self, child: MapPoint) -> None:
        self.children.discard(child)
        child.parents.discard(self)

    def __repr__(self) -> str:
        return f"Point[{self.col},{self.row}]{self.point_type.name}"


def _sort_key(point: MapPoint) -> tuple[int, int]:
    """MapPoint.CompareTo: coord (col, row) tuple order."""
    return (point.col, point.row)


def stable_shuffle(items: list, rng: random.Random, key=None) -> list:
    """ListExtensions.StableShuffle: sort, then Fisher-Yates.

    Makes the result independent of incidental input order (set iteration
    order), which is what keeps the sim's own seeds reproducible.
    """
    items.sort(key=key)
    rng.shuffle(items)
    return items


def gaussian_int(
    rng: random.Random, mean: int, std_dev: int, lo: int, hi: int
) -> int:
    """Rng.NextGaussianInt: Box-Muller, rounded, redrawn until in [lo, hi]."""
    while True:
        d1 = 1.0 - rng.random()
        d2 = 1.0 - rng.random()
        gauss = math.sqrt(-2.0 * math.log(d1)) * math.sin(2.0 * math.pi * d2)
        value = round(mean + std_dev * gauss)
        if lo <= value <= hi:
            return int(value)


@dataclass(frozen=True)
class MapPointTypeCounts:
    """MapPointTypeCounts.cs — how many of each queue-placed type to seat.

    Non-ascension values: 5 elites (`round(5 * 1.6)` = 8 with Swarming
    Elites, not modeled), 3 shops (fixed).
    """

    unknowns: int
    rests: int
    elites: int = _BASE_ELITE_COUNT
    shops: int = 3
    # PointTypesThatIgnoreRules — empty in normal play; kept for fidelity.
    ignore_rules_for: frozenset[MapPointType] = frozenset()

    def should_ignore_rules(self, point_type: MapPointType) -> bool:
        return point_type in self.ignore_rules_for


def standard_unknown_count(rng: random.Random) -> int:
    """MapPointTypeCounts.StandardRandomUnknownCount: gauss(12, 1) in [10, 14]."""
    return gaussian_int(rng, 12, 1, 10, 14)


@dataclass(frozen=True)
class ActMapConfig:
    """The per-act knobs ActModel feeds into StandardActMap.

    `num_rooms` is BaseNumberOfRooms (single-player; the boss and ancient
    floors are extra). `roll_counts` is GetMapPointTypes(mapRng).
    `num_weak_encounters` belongs to room generation (ActModel.GenerateRooms)
    and is carried here so rooms.py can stay act-agnostic too.
    """

    name: str
    num_rooms: int
    roll_counts: Callable[[random.Random], MapPointTypeCounts]
    num_weak_encounters: int


# Transcribed from src/Core/Models/Acts/<Act>.cs (non-ascension values).
OVERGROWTH_MAP = ActMapConfig(
    name="overgrowth",
    num_rooms=15,
    roll_counts=lambda rng: MapPointTypeCounts(
        rests=gaussian_int(rng, 7, 1, 6, 7),
        unknowns=standard_unknown_count(rng),
    ),
    num_weak_encounters=3,
)
UNDERDOCKS_MAP = ActMapConfig(
    name="underdocks",
    num_rooms=15,
    roll_counts=lambda rng: MapPointTypeCounts(
        rests=gaussian_int(rng, 7, 1, 6, 7),
        unknowns=standard_unknown_count(rng),
    ),
    num_weak_encounters=3,
)
HIVE_MAP = ActMapConfig(
    name="hive",
    num_rooms=14,
    roll_counts=lambda rng: MapPointTypeCounts(
        rests=gaussian_int(rng, 6, 1, 6, 7),
        unknowns=standard_unknown_count(rng) - 1,
    ),
    num_weak_encounters=2,
)
GLORY_MAP = ActMapConfig(
    name="glory",
    num_rooms=13,
    roll_counts=lambda rng: MapPointTypeCounts(
        rests=rng.randrange(5, 7),  # Glory.cs: mapRng.NextInt(5, 7)
        unknowns=standard_unknown_count(rng) - 1,
    ),
    num_weak_encounters=2,
)

ACT_MAP_CONFIGS: dict[str, ActMapConfig] = {
    cfg.name: cfg for cfg in (OVERGROWTH_MAP, UNDERDOCKS_MAP, HIVE_MAP, GLORY_MAP)
}

_MAP_WIDTH = 7      # StandardActMap._mapWidth
_NUM_PATHS = 7      # StandardActMap._iterations

# StandardActMap placement restriction sets.
_LOWER_RESTRICTIONS = {MapPointType.REST_SITE, MapPointType.ELITE}
_UPPER_RESTRICTIONS = {MapPointType.REST_SITE}
_PARENT_CHILD_RESTRICTIONS = {
    MapPointType.ELITE,
    MapPointType.REST_SITE,
    MapPointType.TREASURE,
    MapPointType.SHOP,
}
_SIBLING_RESTRICTIONS = {
    MapPointType.REST_SITE,
    MapPointType.MONSTER,
    MapPointType.UNKNOWN,
    MapPointType.ELITE,
    MapPointType.SHOP,
}


class StandardMap:
    """StandardActMap.cs — the generated map for one act.

    grid[col][row] is a MapPoint or None; playable rows are 1..num_rooms.
    `starting_point` (the Ancient, row 0) and `boss_point` (row num_rooms+1)
    live outside the grid, exactly like the source.
    """

    def __init__(
        self,
        rng: random.Random,
        config: ActMapConfig = OVERGROWTH_MAP,
        counts: MapPointTypeCounts | None = None,
        ascension: int = 0,
        has_second_boss: bool = False,
        replace_treasure_with_elites: bool = False,
        enable_pruning: bool = True,
        enable_post_processing: bool = True,
    ) -> None:
        self.rng = rng
        self.config = config
        self.ascension = ascension
        # _mapLength = GetNumberOfRooms + 1 (row 0 stays empty).
        self.map_length = config.num_rooms + 1
        self.grid: list[list[MapPoint | None]] = [
            [None] * self.map_length for _ in range(_MAP_WIDTH)
        ]
        if counts is not None:
            # An explicit override wins outright (mirrors the source's
            # mapPointTypeCountsOverride path, e.g. BigGameHunter).
            self.counts = counts
        else:
            rolled = config.roll_counts(rng)
            # SwarmingElites (Asc 1+): round(5 * 1.6) = 8 elites.
            if ascension >= AscensionLevel.SWARMING_ELITES:
                rolled = replace(rolled, elites=_SWARMING_ELITE_COUNT)
            self.counts = rolled
        self.replace_treasure_with_elites = replace_treasure_with_elites
        self.boss_point = MapPoint(_MAP_WIDTH // 2, self.row_count)
        # DoubleBoss (Asc 10): a second boss one row past the first, reached
        # only through it (StandardActMap.SecondBossMapPoint).
        self.second_boss_point: MapPoint | None = (
            MapPoint(_MAP_WIDTH // 2, self.row_count + 1)
            if has_second_boss
            else None
        )
        self.starting_point = MapPoint(_MAP_WIDTH // 2, 0)
        self.start_points: set[MapPoint] = set()

        self._generate()
        self._assign_point_types()
        if enable_pruning:
            prune_and_repair(self)
        if enable_post_processing:
            center_grid(self.grid)
            spread_adjacent_points(self.grid)
            straighten_paths(self.grid)

    # ── Grid access (ActMap.cs) ──────────────────────────────────────────

    @property
    def column_count(self) -> int:
        return _MAP_WIDTH

    @property
    def row_count(self) -> int:
        return self.map_length

    def all_points(self) -> Iterator[MapPoint]:
        """ActMap.GetAllMapPoints — grid nodes only (no boss/ancient)."""
        for col in range(_MAP_WIDTH):
            for row in range(self.map_length):
                point = self.grid[col][row]
                if point is not None:
                    yield point

    def points_in_row(self, row: int) -> list[MapPoint]:
        if row < 0 or row >= self.map_length:
            return []
        return [
            self.grid[col][row]
            for col in range(_MAP_WIDTH)
            if self.grid[col][row] is not None
        ]

    def get_point(self, col: int, row: int) -> MapPoint | None:
        if (col, row) == self.boss_point.coord:
            return self.boss_point
        if (
            self.second_boss_point is not None
            and (col, row) == self.second_boss_point.coord
        ):
            return self.second_boss_point
        if (col, row) == self.starting_point.coord:
            return self.starting_point
        if 0 <= col < _MAP_WIDTH and 0 <= row < self.map_length:
            return self.grid[col][row]
        return None

    # ── Path carving ─────────────────────────────────────────────────────

    def _get_or_create(self, col: int, row: int) -> MapPoint:
        point = self.grid[col][row]
        if point is None:
            point = MapPoint(col, row)
            self.grid[col][row] = point
        return point

    def _generate(self) -> None:
        """StandardActMap.GenerateMap: 7 shared random-walk paths."""
        for i in range(_NUM_PATHS):
            start = self._get_or_create(self.rng.randrange(_MAP_WIDTH), 1)
            if i == 1:
                # Only the second path is forced onto a fresh start node.
                while start in self.start_points:
                    start = self._get_or_create(self.rng.randrange(_MAP_WIDTH), 1)
            self.start_points.add(start)
            self._path_generate(start)
        for point in self.points_in_row(self.row_count - 1):
            point.add_child(self.boss_point)
        if self.second_boss_point is not None:
            self.boss_point.add_child(self.second_boss_point)
        for point in self.points_in_row(1):
            self.starting_point.add_child(point)

    def _path_generate(self, start: MapPoint) -> None:
        current = start
        while current.row < self.map_length - 1:
            col, row = self._next_coord(current)
            nxt = self._get_or_create(col, row)
            current.add_child(nxt)
            current = nxt

    def _next_coord(self, current: MapPoint) -> tuple[int, int]:
        """GenerateNextCoord: try ±1/0 column steps in shuffled order,
        rejecting X crossovers."""
        left = max(0, current.col - 1)
        right = min(current.col + 1, _MAP_WIDTH - 1)
        offsets = stable_shuffle([-1, 0, 1], self.rng)
        for offset in offsets:
            target = {-1: left, 0: current.col, 1: right}[offset]
            if not self._has_invalid_crossover(current, target):
                return target, current.row + 1
        raise RuntimeError("Cannot find next map node")

    def _has_invalid_crossover(self, current: MapPoint, target_col: int) -> bool:
        """HasInvalidCrossover: a diagonal may not cross the opposite
        diagonal leaving the node beside us."""
        delta = target_col - current.col
        if delta == 0:
            return False
        neighbor = self.grid[target_col][current.row]
        if neighbor is None:
            return False
        return any(
            child.col - neighbor.col == -delta for child in neighbor.children
        )

    # ── Point type assignment ────────────────────────────────────────────

    def _assign_point_types(self) -> None:
        """StandardActMap.AssignPointTypes."""
        for point in self.points_in_row(self.row_count - 1):
            point.point_type = MapPointType.REST_SITE
            point.can_be_modified = False
        mid_type = (
            MapPointType.ELITE
            if self.replace_treasure_with_elites
            else MapPointType.TREASURE
        )
        for point in self.points_in_row(self.row_count - 7):
            point.point_type = mid_type
            point.can_be_modified = False
        for point in self.points_in_row(1):
            point.point_type = MapPointType.MONSTER
            point.can_be_modified = False

        queue: list[MapPointType] = (
            [MapPointType.REST_SITE] * self.counts.rests
            + [MapPointType.SHOP] * self.counts.shops
            + [MapPointType.ELITE] * self.counts.elites
            + [MapPointType.UNKNOWN] * self.counts.unknowns
        )
        self._assign_queue_to_random_points(queue)
        for point in self.all_points():
            if point.point_type == MapPointType.UNASSIGNED:
                point.point_type = MapPointType.MONSTER
        self.boss_point.point_type = MapPointType.BOSS
        self.starting_point.point_type = MapPointType.ANCIENT
        if self.second_boss_point is not None:
            self.second_boss_point.point_type = MapPointType.BOSS

    def _assign_queue_to_random_points(self, queue: list[MapPointType]) -> None:
        """AssignRemainingTypesToRandomPoints: up to 3 shuffled passes."""
        for _ in range(3):
            if not queue:
                break
            unassigned = [
                p for p in self.all_points()
                if p.point_type == MapPointType.UNASSIGNED
            ]
            stable_shuffle(unassigned, self.rng, key=_sort_key)
            for point in unassigned:
                if not queue:
                    break
                point.point_type = self._next_valid_type(queue, point)

    def _next_valid_type(
        self, queue: list[MapPointType], point: MapPoint
    ) -> MapPointType:
        """GetNextValidPointType: cycle the queue once looking for a type
        legal at this point; illegal types go to the back."""
        for _ in range(len(queue)):
            point_type = queue.pop(0)
            if self.counts.should_ignore_rules(point_type):
                return point_type
            if self.is_valid_point_type(point_type, point):
                return point_type
            queue.append(point_type)
        return MapPointType.UNASSIGNED

    # ── Placement legality (used by assignment AND repair) ──────────────

    def is_valid_point_type(
        self, point_type: MapPointType, point: MapPoint
    ) -> bool:
        return (
            self._valid_for_upper(point_type, point)
            and self._valid_for_lower(point_type, point)
            and self._valid_with_parents(point_type, point)
            and self._valid_with_children(point_type, point)
            and self._valid_with_siblings(point_type, point)
        )

    @staticmethod
    def _valid_for_lower(point_type: MapPointType, point: MapPoint) -> bool:
        """No rest sites or elites below row 6."""
        if point.row < 6:
            return point_type not in _LOWER_RESTRICTIONS
        return True

    def _valid_for_upper(self, point_type: MapPointType, point: MapPoint) -> bool:
        """No rest sites in the top 3 grid rows (the forced pre-boss rest
        row is assigned directly and skips this)."""
        if point.row >= self.map_length - 3:
            return point_type not in _UPPER_RESTRICTIONS
        return True

    @staticmethod
    def _valid_with_parents(point_type: MapPointType, point: MapPoint) -> bool:
        """Elite/Rest/Treasure/Shop can't neighbor the same type."""
        if point_type in _PARENT_CHILD_RESTRICTIONS:
            return not any(
                p.point_type == point_type
                for p in list(point.parents) + list(point.children)
            )
        return True

    @staticmethod
    def _valid_with_children(point_type: MapPointType, point: MapPoint) -> bool:
        if point_type in _PARENT_CHILD_RESTRICTIONS:
            return not any(c.point_type == point_type for c in point.children)
        return True

    @staticmethod
    def _valid_with_siblings(point_type: MapPointType, point: MapPoint) -> bool:
        """A fork never offers two of the restricted types side by side."""
        if point_type in _SIBLING_RESTRICTIONS:
            siblings = {
                sib
                for parent in point.parents
                for sib in parent.children
                if sib is not point
            }
            return not any(s.point_type == point_type for s in siblings)
        return True


# ═════════════════════════════════════════════════════════════════════════
# Pruning (MapPathPruning.cs) — remove duplicate path segments, then
# repair point-type counts the removals knocked below target.
# ═════════════════════════════════════════════════════════════════════════

def prune_and_repair(act_map: StandardMap) -> None:
    """MapPathPruning.PruneAndRepair: prune → repair, up to 3 rounds
    (repair can create fresh duplicates)."""
    for _ in range(3):
        prune_duplicate_segments(act_map)
        if not _repair_pruned_point_types(act_map):
            break


def prune_duplicate_segments(act_map: StandardMap) -> None:
    """Full prune loop: rescan and prune until no duplicates remain."""
    iterations = 0
    matching = find_matching_segments(act_map.starting_point)
    while _prune_paths(act_map, matching):
        iterations += 1
        if iterations > 50:
            raise RuntimeError("Unable to prune matching segments")
        matching = find_matching_segments(act_map.starting_point)


def find_matching_segments(
    starting_point: MapPoint,
) -> list[list[list[MapPoint]]]:
    """Groups of non-overlapping segments that share a key (same start/end
    anchors and identical point-type sequence). Groups come back in sorted
    key order (the source uses an ordinal SortedDictionary).

    This is the hot loop of map generation (rescanned after every prune
    action), so it deviates from a line-by-line port for speed while staying
    result-identical: segments are keyed on (anchor, type-bytes) tuples, and
    the source's string key is only rebuilt for the few duplicate groups to
    reproduce the SortedDictionary's ordinal order. The tuple and string
    keys are injective images of each other, so grouping is unchanged."""
    segments: dict[tuple, _SegmentGroup] = {}
    processed: set[tuple[int, ...]] = set()
    for path in _find_all_paths(starting_point):
        _add_segments(path, segments, processed)
    duplicates = [
        (_ordinal_key(key), entry.group)
        for key, entry in segments.items()
        if len(entry.group) > 1
    ]
    duplicates.sort(key=lambda item: item[0])
    return [group for _key, group in duplicates]


def _find_all_paths(current: MapPoint) -> list[list[MapPoint]]:
    """FindAllPaths: every route from `current` to the boss.

    Suffix path lists are memoized per invocation (the map is static within
    one scan) — the plain recursion re-enumerates a node's subtree once per
    route reaching that node. Output order is exactly the recursion's."""
    memo: dict[MapPoint, list[list[MapPoint]]] = {}

    def paths_from(node: MapPoint) -> list[list[MapPoint]]:
        cached = memo.get(node)
        if cached is not None:
            return cached
        if node.point_type == MapPointType.BOSS:
            result = [[node]]
        else:
            result = [
                [node] + suffix
                for child in node.children  # insertion order == game HashSet order
                for suffix in paths_from(child)
            ]
        memo[node] = result
        return result

    return paths_from(current)


@dataclass
class _SegmentGroup:
    """One key's accepted segments plus the interior id tuples that make the
    overlap scan cheap."""

    group: list[list[MapPoint]]        # accepted segments, insertion order
    interiors: list[tuple[int, ...]]   # their interior node ids, same order


def _add_segments(
    path: list[MapPoint],
    segments: dict[tuple, _SegmentGroup],
    processed: set[tuple[int, ...]],
) -> None:
    """AddSegmentsToDictionary: every junction-to-merge slice of a path.

    Result-identical to the source, restructured for speed: point types,
    node ids and the merge rows (valid segment ends) are precomputed per
    path, and a candidate walk identical to one already processed this scan
    — the overwhelmingly common case, since every path routing through a
    physical segment re-enumerates it — is skipped via the scan-wide
    ``processed`` set before any key is built. (An identical walk always
    keys identically and is always rejected on re-encounter: it overlaps
    whatever its twin overlapped, or its accepted twin itself, and groups
    only ever grow.) The positional interior-overlap scan
    (OverlappingSegment: ``a[i] is b[i]`` for interior i) runs only for
    genuinely new walks, on precomputed id tuples."""
    type_bytes = bytes(p.point_type for p in path)
    path_ids = [id(p) for p in path]
    n = len(path)
    # Rows where paths merge back together (valid segment ends), ascending.
    merge_idx = [k for k in range(2, n) if len(path[k].parents) >= 2]
    if not merge_idx:
        return
    for i in range(n - 1):
        start = path[i]
        # Segments start at a fork (or the very bottom of the map).
        if len(start.children) <= 1 and start.row != 0:
            continue
        row0 = start.row == 0
        for k in merge_idx:
            if k < i + 2:
                continue
            stop = k + 1
            ids = tuple(path_ids[i:stop])
            if ids in processed:
                continue
            processed.add(ids)
            end = path[k]
            # Row-0 starts key on the row alone (all bottom starts are
            # interchangeable), mirroring GenerateSegmentKey.
            if row0:
                key = (0, end.col, end.row, type_bytes[i:stop])
            else:
                key = (1, start.col, start.row, end.col, end.row,
                       type_bytes[i:stop])
            entry = segments.get(key)
            if entry is None:
                segments[key] = _SegmentGroup(
                    group=[path[i:stop]], interiors=[ids[1:-1]])
                continue
            interior = ids[1:-1]
            if not any(
                any(x == y for x, y in zip(existing, interior))
                for existing in entry.interiors
            ):
                entry.group.append(path[i:stop])
                entry.interiors.append(interior)


def _ordinal_key(key: tuple) -> str:
    """GenerateSegmentKey's string, rebuilt from the tuple key — needed only
    for the few duplicate groups, to reproduce the ordinal sort order."""
    if key[0] == 0:
        _, last_col, last_row, type_bytes = key
        prefix = f"0-{last_col},{last_row}-"
    else:
        _, first_col, first_row, last_col, last_row, type_bytes = key
        prefix = f"{first_col},{first_row}-{last_col},{last_row}-"
    return prefix + ",".join(map(str, type_bytes))


def _prune_paths(
    act_map: StandardMap, matching: list[list[list[MapPoint]]]
) -> bool:
    """PrunePaths: handle one duplicate group per call (then rescan)."""
    for group in matching:
        act_map.rng.shuffle(group)
        if _prune_all_but_last(act_map, group) != 0:
            return True
        if _break_parent_child_in_any(group):
            return True
    return False


def _prune_all_but_last(
    act_map: StandardMap, matches: list[list[MapPoint]]
) -> int:
    pruned = 0
    for segment in matches:
        if pruned == len(matches) - 1:
            return pruned
        if _prune_segment(act_map, segment):
            pruned += 1
    return pruned


def _prune_segment(act_map: StandardMap, segment: list[MapPoint]) -> bool:
    """PruneSegment: delete removable interior nodes of a redundant
    segment. A node is only removable when it is a pure pass-through and
    deleting it strands nothing."""
    result = False
    for i in range(len(segment) - 1):
        point = segment[i]
        if not _is_in_map(act_map, point):
            return True  # already removed by an earlier group
        if (
            len(point.children) > 1
            or len(point.parents) > 1
            or any(
                len(parent.children) == 1 and not _is_removed(act_map, parent)
                for parent in point.parents
            )
        ):
            continue
        rest = segment[i:]
        if any(len(n.children) > 1 and len(n.parents) == 1 for n in rest):
            continue
        if len(segment[-1].parents) == 1:
            return False
        if not any(
            len(child.parents) == 1
            for child in point.children
            if child not in segment
        ):
            _remove_point(act_map, point)
            result = True
    return result


def _remove_point(act_map: StandardMap, point: MapPoint) -> None:
    act_map.grid[point.col][point.row] = None
    act_map.start_points.discard(point)
    for child in list(point.children):
        point.remove_child(child)
    for parent in list(point.parents):
        parent.remove_child(point)


def _is_in_map(act_map: StandardMap, point: MapPoint) -> bool:
    if act_map.grid[point.col][point.row] is None:
        return point.point_type in (MapPointType.ANCIENT, MapPointType.BOSS)
    return True


def _is_removed(act_map: StandardMap, point: MapPoint) -> bool:
    return act_map.grid[point.col][point.row] is None


def _break_parent_child_in_any(matches: list[list[MapPoint]]) -> bool:
    """When no node can be removed, cut a redundant edge instead."""
    for segment in matches:
        if _break_parent_child(segment):
            return True
    return False


def _break_parent_child(segment: list[MapPoint]) -> bool:
    result = False
    for i in range(len(segment) - 1):
        point = segment[i]
        if len(point.children) >= 2:
            nxt = segment[i + 1]
            if len(nxt.parents) != 1:
                point.remove_child(nxt)
                result = True
    return result


def _repair_pruned_point_types(act_map: StandardMap) -> bool:
    """RepairPrunedPointTypes: top shops/elites/rests/unknowns back up to
    their target counts by converting random legal Monster nodes."""
    counts = act_map.counts
    repaired = False
    for point_type, target in (
        (MapPointType.SHOP, counts.shops),
        (MapPointType.ELITE, counts.elites),
        (MapPointType.REST_SITE, counts.rests),
        (MapPointType.UNKNOWN, counts.unknowns),
    ):
        repaired |= _repair_point_type(act_map, point_type, target)
    return repaired


def _repair_point_type(
    act_map: StandardMap, point_type: MapPointType, target: int
) -> bool:
    have = sum(1 for p in act_map.all_points() if p.point_type == point_type)
    missing = target - have
    if missing <= 0:
        return False
    result = False
    candidates = [
        p
        for p in act_map.all_points()
        if p.point_type == MapPointType.MONSTER and p.can_be_modified
    ]
    stable_shuffle(candidates, act_map.rng, key=_sort_key)
    for point in candidates:
        if missing == 0:
            break
        if act_map.is_valid_point_type(point_type, point):
            point.point_type = point_type
            missing -= 1
            result = True
    return result


# ═════════════════════════════════════════════════════════════════════════
# Post-processing (MapPostProcessing.cs) — cosmetic column moves only;
# topology (parents/children) never changes.
# ═════════════════════════════════════════════════════════════════════════

def _column_empty(grid: list[list[MapPoint | None]], col: int) -> bool:
    return all(cell is None for cell in grid[col])


def center_grid(grid: list[list[MapPoint | None]]) -> None:
    """CenterGrid: shift everything by one if two edge columns are empty
    on one side only."""
    width = len(grid)
    rows = len(grid[0])
    left_empty = _column_empty(grid, 0) and _column_empty(grid, 1)
    right_empty = _column_empty(grid, width - 1) and _column_empty(grid, width - 2)
    shift = 0
    if left_empty and not right_empty:
        shift = -1
    elif right_empty and not left_empty:
        shift = 1
    if shift == 0:
        return
    cols = range(width - 1, -1, -1) if shift > 0 else range(width)
    for row in range(rows):
        for col in cols:
            point = grid[col][row]
            grid[col][row] = None
            new_col = col + shift
            if 0 <= new_col < width:
                grid[new_col][row] = point
                if point is not None:
                    point.col = new_col


def _allowed_columns(point: MapPoint, width: int) -> set[int]:
    """A node must stay within ±1 column of every parent and child."""
    allowed = set(range(width))
    for neighbor in list(point.parents) + list(point.children):
        allowed &= {
            c
            for c in (neighbor.col - 1, neighbor.col, neighbor.col + 1)
            if 0 <= c < width
        }
    return allowed


def _min_gap(candidate_col: int, row_points: list[MapPoint], current: MapPoint) -> int:
    gaps = [
        abs(candidate_col - p.col) for p in row_points if p is not current
    ]
    return min(gaps) if gaps else int(1e9)


def spread_adjacent_points(grid: list[list[MapPoint | None]]) -> None:
    """SpreadAdjacentMapPoints: within each row, greedily move nodes to
    maximize the gap to their row neighbors, respecting connectivity."""
    width = len(grid)
    rows = len(grid[0])
    for row in range(rows):
        row_points = [
            grid[col][row] for col in range(width) if grid[col][row] is not None
        ]
        moved = True
        while moved:
            moved = False
            for point in row_points:
                col = point.col
                best_col, best_gap = col, _min_gap(col, row_points, point)
                for candidate in _allowed_columns(point, width):
                    if candidate == col:
                        continue
                    if grid[candidate][row] not in (None, point):
                        continue
                    gap = _min_gap(candidate, row_points, point)
                    if gap > best_gap:
                        best_col, best_gap = candidate, gap
                if best_col != col:
                    grid[col][row] = None
                    grid[best_col][row] = point
                    point.col = best_col
                    moved = True


def straighten_paths(grid: list[list[MapPoint | None]]) -> None:
    """StraightenPaths: un-kink single-link zigzag nodes."""
    width = len(grid)
    rows = len(grid[0])
    for row in range(rows):
        for col in range(width):
            point = grid[col][row]
            if point is None or len(point.parents) != 1 or len(point.children) != 1:
                continue
            parent = next(iter(point.parents))
            child = next(iter(point.children))
            pokes_left = point.col < child.col and point.col < parent.col
            pokes_right = point.col > child.col and point.col > parent.col
            if pokes_left and col < width - 1:
                if grid[col + 1][row] is not None:
                    continue
                point.col = col + 1
                grid[col][row] = None
                grid[col + 1][row] = point
            if pokes_right and col > 0 and grid[col - 1][row] is None:
                point.col = col - 1
                grid[col][row] = None
                grid[col - 1][row] = point


# ═════════════════════════════════════════════════════════════════════════
# Golden path (GoldenPathActMap.cs) — the fixed single-column 16-room map.
# Handy as a deterministic fixture and a linear training curriculum.
# ═════════════════════════════════════════════════════════════════════════

_GOLDEN_PATH_TYPES = (
    MapPointType.MONSTER,
    MapPointType.UNKNOWN,
    MapPointType.MONSTER,
    MapPointType.REST_SITE,
    MapPointType.MONSTER,
    MapPointType.REST_SITE,
    MapPointType.UNKNOWN,
    MapPointType.TREASURE,
    MapPointType.UNKNOWN,
    MapPointType.TREASURE,
    MapPointType.UNKNOWN,
    MapPointType.SHOP,
    MapPointType.ELITE,
    MapPointType.REST_SITE,
    MapPointType.ELITE,
    MapPointType.REST_SITE,
)


def golden_path_map(
    rng: random.Random | None = None,
    config: ActMapConfig = OVERGROWTH_MAP,
) -> StandardMap:
    """Build a StandardMap-shaped object with the golden path layout."""
    fixed = StandardMap.__new__(StandardMap)
    fixed.rng = rng or random.Random()
    fixed.config = config
    fixed.ascension = 0
    fixed.map_length = len(_GOLDEN_PATH_TYPES) + 1
    fixed.grid = [[None] * fixed.map_length for _ in range(_MAP_WIDTH)]
    fixed.counts = MapPointTypeCounts(unknowns=0, rests=0, elites=0, shops=0)
    fixed.replace_treasure_with_elites = False
    fixed.boss_point = MapPoint(_MAP_WIDTH // 2, fixed.row_count)
    fixed.boss_point.point_type = MapPointType.BOSS
    fixed.second_boss_point = None
    fixed.starting_point = MapPoint(_MAP_WIDTH // 2, 0)
    fixed.starting_point.point_type = MapPointType.ANCIENT
    fixed.start_points = set()
    previous: MapPoint | None = None
    for i, point_type in enumerate(_GOLDEN_PATH_TYPES):
        point = MapPoint(3, i + 1)
        point.point_type = point_type
        fixed.grid[3][i + 1] = point
        if previous is not None:
            previous.add_child(point)
        previous = point
    fixed.start_points.add(fixed.grid[3][1])
    fixed.grid[3][fixed.row_count - 1].add_child(fixed.boss_point)
    fixed.starting_point.add_child(fixed.grid[3][1])
    return fixed


# ═════════════════════════════════════════════════════════════════════════
# Spoils map (SpoilsActMap.cs) — the hourglass map the Spoils Map card forces
# in Act 2: every path is funnelled through one centered treasure node, then
# fans back out. Generated from scratch (the source keeps it separate from
# StandardActMap because the converging topology can't come from post-
# processing). The placement legality rules are identical to StandardMap's,
# so this subclass reuses them; only carving and forced-row assignment differ,
# and there is NO cosmetic post-processing (it would break the hourglass).
# ═════════════════════════════════════════════════════════════════════════

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


class SpoilsActMap(StandardMap):
    """SpoilsActMap.cs — the Spoils Map card's hourglass map.

    Reuses StandardMap's grid access, legality checks, queue assignment, and
    the MapPathPruning port; overrides only the carving (converging paths) and
    the forced-row assignment (the treasure is a single centered node placed
    during carving, not a whole row).
    """

    def __init__(
        self,
        rng: random.Random,
        config: ActMapConfig = UNDERDOCKS_MAP,
        counts: MapPointTypeCounts | None = None,
        ascension: int = 0,
    ) -> None:
        self.rng = rng
        self.config = config
        self.ascension = ascension
        self.map_length = config.num_rooms + 1
        self.grid = [[None] * self.map_length for _ in range(_MAP_WIDTH)]
        if counts is not None:
            self.counts = counts
        else:
            rolled = config.roll_counts(rng)
            if ascension >= AscensionLevel.SWARMING_ELITES:
                rolled = replace(rolled, elites=_SWARMING_ELITE_COUNT)
            self.counts = rolled
        self.replace_treasure_with_elites = False
        # SpoilsActMap: _treasureRow = GetRowCount() - 7 (same as the forced
        # treasure row of a standard act).
        self._treasure_row = self.row_count - 7
        self.boss_point = MapPoint(_MAP_WIDTH // 2, self.row_count)
        self.second_boss_point = None
        self.starting_point = MapPoint(_MAP_WIDTH // 2, 0)
        self.start_points = set()

        self._generate_hourglass()
        self._assign_point_types_spoils()
        prune_and_repair(self)

    # ── Hourglass carving ────────────────────────────────────────────────

    def _generate_hourglass(self) -> None:
        """SpoilsActMap.GenerateHourglassMap."""
        center = _MAP_WIDTH // 2
        if self._treasure_row <= 0 or self._treasure_row >= self.row_count:
            raise ValueError("Treasure row is out of bounds for SpoilsActMap")
        for i in range(_NUM_PATHS):
            start = self._get_or_create(self.rng.randrange(_MAP_WIDTH), 1)
            if i == 1:
                while start in self.start_points:
                    start = self._get_or_create(
                        self.rng.randrange(_MAP_WIDTH), 1
                    )
            self.start_points.add(start)
            self._path_generate_spoils(start)
        treasure = self._get_or_create(center, self._treasure_row)
        treasure.point_type = MapPointType.TREASURE
        treasure.can_be_modified = False
        for point in list(self.points_in_row(self._treasure_row)):
            if point is not treasure:
                self._redirect_to_treasure(point, treasure)
        self._connect_row_to_boss()
        self._connect_row_to_start()

    def _path_generate_spoils(self, start: MapPoint) -> None:
        current = start
        while current.row < self.map_length - 1:
            col, row = self._next_coord_spoils(current)
            nxt = self._get_or_create(col, row)
            current.add_child(nxt)
            current = nxt

    def _next_coord_spoils(self, current: MapPoint) -> tuple[int, int]:
        """SpoilsActMap.GenerateNextCoord: bias toward the center column while
        approaching the treasure row (so paths converge), stay within the
        hourglass's per-row column window, and cap parents/children at 3."""
        row = current.row + 1
        min_col, max_col = self._allowed_columns_for_row(row)
        center = _MAP_WIDTH // 2
        dist = self._treasure_row - current.row
        if dist > 3 or dist <= 0:
            offsets = stable_shuffle([-1, 0, 1], self.rng)
        else:
            offsets = _centered_priority_list(current.col, center)
        for offset in offsets:
            next_col = _next_column(current.col, offset)
            if (
                next_col < min_col
                or next_col > max_col
                or self._has_invalid_crossover(current, next_col)
            ):
                continue
            point = self.get_point(next_col, row)
            parents_ok = (
                point is None
                or current in point.parents
                or len(point.parents) < 3
            )
            children_ok = (
                current is self.starting_point
                or len(current.children) < 3
                or (point is not None and point in current.children)
            )
            if parents_ok and children_ok:
                return next_col, row
        # Fallback: step toward center within the allowed window.
        col = _clamp(center, min_col, max_col)
        if abs(col - current.col) > 1:
            col = _clamp(
                current.col + _sign(col - current.col), min_col, max_col
            )
        if self._has_invalid_crossover(current, col):
            col = _clamp(current.col, min_col, max_col)
        return col, row

    def _allowed_columns_for_row(self, row: int) -> tuple[int, int]:
        """SpoilsActMap.GetAllowedColumnsForRow: the column window narrows to
        the center at the treasure row and near the top, widening elsewhere."""
        center = _MAP_WIDTH // 2
        to_treasure = abs(row - self._treasure_row)
        to_top = self.map_length - 1 - row
        cap = min(center, max(0, to_top) + 1)
        half_width = min(center, min(to_treasure, cap))
        return max(0, center - half_width), min(_MAP_WIDTH - 1, center + half_width)

    def _redirect_to_treasure(
        self, stray: MapPoint, treasure: MapPoint
    ) -> None:
        """SpoilsActMap.RedirectToTreasure: rewire a stray treasure-row node's
        edges through the single treasure node, then drop it from the grid."""
        for parent in list(stray.parents):
            parent.remove_child(stray)
            parent.add_child(treasure)
        for child in list(stray.children):
            stray.remove_child(child)
            treasure.add_child(child)
        self.grid[stray.col][stray.row] = None

    def _connect_row_to_boss(self) -> None:
        top = self.row_count - 1
        for col in range(_MAP_WIDTH):
            point = self.grid[col][top]
            if point is not None and self.boss_point not in point.children:
                point.add_child(self.boss_point)

    def _connect_row_to_start(self) -> None:
        for col in range(_MAP_WIDTH):
            point = self.grid[col][1]
            if point is not None and point not in self.starting_point.children:
                self.starting_point.add_child(point)

    # ── Point types ──────────────────────────────────────────────────────

    def _assign_point_types_spoils(self) -> None:
        """SpoilsActMap.AssignPointTypes: force the top rest row and the row-1
        monsters (the treasure node was fixed during carving), then run the
        same queue placement as a standard act."""
        for point in self.points_in_row(self.row_count - 1):
            point.point_type = MapPointType.REST_SITE
            point.can_be_modified = False
        for point in self.points_in_row(1):
            point.point_type = MapPointType.MONSTER
            point.can_be_modified = False
        queue: list[MapPointType] = (
            [MapPointType.REST_SITE] * self.counts.rests
            + [MapPointType.SHOP] * self.counts.shops
            + [MapPointType.ELITE] * self.counts.elites
            + [MapPointType.UNKNOWN] * self.counts.unknowns
        )
        self._assign_queue_to_random_points(queue)
        for point in self.all_points():
            if point.point_type == MapPointType.UNASSIGNED:
                point.point_type = MapPointType.MONSTER
        self.boss_point.point_type = MapPointType.BOSS
        self.starting_point.point_type = MapPointType.ANCIENT


def _centered_priority_list(current_col: int, center_col: int) -> list[int]:
    """SpoilsActMap.BuildCenteredPriorityList: try the center-ward step first,
    then straight, then away, filling in any missing ±1 offsets."""
    result: list[int] = []
    toward = _sign(center_col - current_col)
    if toward != 0:
        result.append(toward)
    result.append(0)
    if toward != 0:
        result.append(-toward)
    if -1 not in result:
        result.append(-1)
    if 1 not in result:
        result.append(1)
    return result


def _next_column(current_col: int, direction: int) -> int:
    """SpoilsActMap.GetNextColumn."""
    if direction == -1:
        return max(0, current_col - 1)
    if direction == 1:
        return min(_MAP_WIDTH - 1, current_col + 1)
    return current_col
