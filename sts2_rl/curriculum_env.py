"""STS2CurriculumRunEnv — the phase-1 curriculum env: a full run on a
randomized single-column map, rewarded by floors reached and nothing else.

Design (see RL.md for the base env):

  1. **Floor-only reward.** Reward is `floor_reward` x floors gained (0/1)
     plus a terminal `reward_win`. No HP-delta term — the critic learns
     "low HP -> fewer future floors" from the observation via GAE instead
     of hand-coded shaping. Needs the long-horizon credit assignment of
     gamma~=0.999 (train_torch.py's default for --env column).

  2. **Randomized single-column maps.** Every act is one column to the
     boss (GoldenPathActMap shape), room-type sequence re-sampled every act
     from `room_weights` (monster-heavy by default). One column forces
     every fight (no risk-averse route-dodging); re-sampling prevents
     memorizing the schedule, so reading the map-lookahead observation is
     the only way to prepare — the skill that transfers to real branching
     maps. "?" floors always resolve to Events (Golden Compass semantics).

Phase 2 is the unmodified STS2RunEnv with the same floor-only reward
defaults; obs/action layout is IDENTICAL (only the RunState factory
differs), so checkpoints trained here resume directly on --env run.

The column obeys StandardActMap's placement rules projected onto a single
path: forced rows (row 1 Monster, row `n_rooms - 6` Treasure, top row
Rest), no Elite/Rest below row 6, no Rest in the top 3 rows, no repeated
special room (elite/rest/treasure/shop) on consecutive floors — same
restriction sets as actmap.py. Deliberately non-faithful: type
*frequencies* come from `room_weights` (calibrated to the measured
real-map mix) rather than per-map queue counts, and the map-modifier
relic/card pipeline (Spoils Map, Golden Compass regen) is skipped — the
column IS the map.
"""
from __future__ import annotations

import random

from .actmap import (
    ActMapConfig,
    MapPoint,
    MapPointType,
    MapPointTypeCounts,
    OVERGROWTH_MAP,
    StandardMap,
    _LOWER_RESTRICTIONS,
    _MAP_WIDTH,
    _PARENT_CHILD_RESTRICTIONS,
    _UPPER_RESTRICTIONS,
)
from .characters import Character, DEFAULT_CHARACTER
from .run import RunState
from .run_env import STS2RunEnv

# ── Column sampling ──────────────────────────────────────────────────────

# Default per-floor room-type weights, calibrated to the measured non-forced
# node mix of real StandardMaps (500 seeds/act: queue rests ~6.5, shops 3,
# elites 5, unknowns ~12, leftover Monsters ~22 of ~49 non-forced nodes).
# Treasure is 0 because real maps place treasure ONLY on the forced row —
# the sampler forces floor n_rooms−6 to Treasure just like the game.
# Still combat-heavy in practice (~6-8 fights/act vs the golden path's 5).
# UNKNOWN floors resolve to Events.
DEFAULT_ROOM_WEIGHTS: dict[str, float] = {
    "monster": 0.46,
    "elite": 0.10,
    "event": 0.25,
    "rest": 0.13,
    "treasure": 0.00,
    "shop": 0.06,
}

_WEIGHT_KEY_TO_TYPE: dict[str, MapPointType] = {
    "monster": MapPointType.MONSTER,
    "elite": MapPointType.ELITE,
    "event": MapPointType.UNKNOWN,   # "?" — forced to Event on entry
    "rest": MapPointType.REST_SITE,
    "treasure": MapPointType.TREASURE,
    "shop": MapPointType.SHOP,
}

# StandardActMap's own restriction sets, reused so the column provably obeys
# the same rules: _PARENT_CHILD_RESTRICTIONS (elite/rest/treasure/shop can't
# neighbor the same type — Monster and "?" may chain), _LOWER_RESTRICTIONS
# (no rest/elite below row 6), _UPPER_RESTRICTIONS (no rest in the top 3
# rows; the forced pre-boss rest is assigned directly and skips the check).
_NO_REPEAT_TYPES = frozenset(_PARENT_CHILD_RESTRICTIONS)


def random_column_types(
    rng: random.Random,
    n_rooms: int = 16,
    room_weights: dict[str, float] | None = None,
    min_special_floor: int = 6,
) -> tuple[MapPointType, ...]:
    """Sample a column's room-type sequence (floor 1 → floor `n_rooms`).

    Constraints — StandardActMap's placement rules projected onto a single
    column (see actmap.py's _assign_point_types / is_valid_point_type):

      - forced rows: floor 1 is Monster, floor ``n_rooms − 6`` is Treasure
        (the treasure row, row_count − 7), the top floor is a Rest Site
        (the pre-boss rest);
      - ``_valid_for_lower``: no Elite or Rest Site below floor
        `min_special_floor` (the game uses row < 6);
      - ``_valid_for_upper``: no Rest Site in the top 3 rows
        (floor ≥ ``n_rooms − 2``) besides the forced top rest;
      - ``_valid_with_parents/children``: elite/rest/treasure/shop never
        repeat on consecutive floors (including against forced rows).

    Sibling rules don't apply — a column has no forks.
    """
    if n_rooms < 3:
        raise ValueError("a column needs at least 3 rooms (monster … rest)")
    weights = dict(DEFAULT_ROOM_WEIGHTS if room_weights is None else room_weights)
    unknown = set(weights) - set(_WEIGHT_KEY_TO_TYPE)
    if unknown:
        raise ValueError(
            f"unknown room_weights keys {sorted(unknown)}; "
            f"valid: {sorted(_WEIGHT_KEY_TO_TYPE)}"
        )
    population = [_WEIGHT_KEY_TO_TYPE[k] for k in weights]
    weight_values = list(weights.values())
    if not any(w > 0 for w in weight_values):
        raise ValueError("room_weights must have at least one positive weight")

    forced: dict[int, MapPointType] = {
        1: MapPointType.MONSTER,
        n_rooms: MapPointType.REST_SITE,
    }
    treasure_floor = n_rooms - 6             # StandardActMap: row_count - 7
    if 1 < treasure_floor < n_rooms:
        forced[treasure_floor] = MapPointType.TREASURE

    types: list[MapPointType] = []
    for floor in range(1, n_rooms + 1):
        if floor in forced:
            types.append(forced[floor])
            continue
        choice = MapPointType.MONSTER        # always-legal fallback
        for _ in range(32):
            t = rng.choices(population, weight_values)[0]
            if t in _LOWER_RESTRICTIONS and floor < min_special_floor:
                continue
            if t in _UPPER_RESTRICTIONS and floor >= n_rooms - 2:
                continue
            if t in _NO_REPEAT_TYPES and (
                types[-1] == t or forced.get(floor + 1) == t
            ):
                continue
            choice = t
            break
        types.append(choice)
    return tuple(types)


def column_map(
    rng: random.Random,
    config: ActMapConfig = OVERGROWTH_MAP,
    types: tuple[MapPointType, ...] = (),
) -> StandardMap:
    """A StandardMap-shaped single column with the given type sequence —
    actmap.golden_path_map's construction, minus its fixed type tuple."""
    if not types:
        types = random_column_types(rng, n_rooms=config.num_rooms)
    fixed = StandardMap.__new__(StandardMap)
    fixed.rng = rng
    fixed.config = config
    fixed.ascension = 0
    fixed.map_length = len(types) + 1
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
    for i, point_type in enumerate(types):
        point = MapPoint(_MAP_WIDTH // 2, i + 1)
        point.point_type = point_type
        fixed.grid[_MAP_WIDTH // 2][i + 1] = point
        if previous is not None:
            previous.add_child(point)
        previous = point
    fixed.start_points.add(fixed.grid[_MAP_WIDTH // 2][1])
    fixed.grid[_MAP_WIDTH // 2][fixed.row_count - 1].add_child(fixed.boss_point)
    fixed.starting_point.add_child(fixed.grid[_MAP_WIDTH // 2][1])
    return fixed


# ── Run state ────────────────────────────────────────────────────────────

class ColumnRunState(RunState):
    """RunState whose every act map is a freshly sampled random column.

    Overrides the two map hooks: `_generate_map` returns the column directly
    (the relic/card map-modifier pipeline is skipped — Spoils Map and Golden
    Compass would fight the column; a Neow Golden Compass still triggers
    `regenerate_map`, which harmlessly re-samples the column before any
    travel), and `_unknown_allowed_room_types` pins "?" floors to Event
    (Golden Compass semantics) so combat density is exactly what was
    sampled. Room/encounter queues still come from the act's real pools and
    wrap if a monster-heavy column outruns them (RoomSet semantics).
    """

    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        column_rooms: int | None = None,
        room_weights: dict[str, float] | None = None,
        min_special_floor: int = 6,
        branch_prob: float = 0.0,
        character: "str | Character" = DEFAULT_CHARACTER,
    ) -> None:
        super().__init__(rng=rng, character=character)
        self._column_rooms = column_rooms
        self._room_weights = room_weights
        self._min_special_floor = min_special_floor
        self._branch_prob = branch_prob
        # Per-episode branch/column decision. The `branch_prob > 0.0` guard
        # is load-bearing: at branch_prob=0.0 no extra RNG draw happens, so
        # the env stays bit-identical to the pre-annealing column env.
        self._branching = (
            branch_prob > 0.0 and rng is not None and rng.random() < branch_prob
        )

    def _generate_map(self):
        if self._branching:
            # Real StandardMap + relic/card modifier pipeline.
            return super()._generate_map()
        # column_rooms=None follows the act's real room count (Overgrowth/
        # Underdocks 15, Hive 14, Glory 13) like a real run does.
        n_rooms = (
            self._column_rooms
            if self._column_rooms is not None
            else self.act_config.num_rooms
        )
        types = random_column_types(
            self.rng,
            n_rooms=n_rooms,
            room_weights=self._room_weights,
            min_special_floor=self._min_special_floor,
        )
        return column_map(self.rng, self.act_config, types)

    def _unknown_allowed_room_types(self, blacklist) -> set:
        if self._branching:
            return super()._unknown_allowed_room_types(blacklist)
        from .rooms import RoomType

        return {RoomType.EVENT}


# ── Environment ──────────────────────────────────────────────────────────

class STS2CurriculumRunEnv(STS2RunEnv):
    """STS2RunEnv on randomized single-column maps with floor-only reward.

    Same observation/action layout, RUN_OBS_SCHEMA_VERSION and reward
    defaults as the parent (STS2RunEnv defaults to this curriculum's
    floor-only reward:

      reward     = floor_reward × floors gained        (the metric)
                 + reward_win on final-boss victory    (a few floors' worth)

    hp/act shaping default to 0 — the critic derives HP's value from the
    observation; see the module docstring) — checkpoints move freely between
    this env and STS2RunEnv. Only the RunState factory (column maps)
    differs. All parent kwargs (acts, card_obs, max_steps, …) pass through.
    """

    def __init__(
        self,
        *,
        column_rooms: int | None = None,
        room_weights: dict[str, float] | None = None,
        min_special_floor: int = 6,
        branch_prob: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._column_rooms = column_rooms
        self._room_weights = dict(room_weights) if room_weights is not None else None
        self._min_special_floor = min_special_floor
        self._branch_prob = branch_prob

    def _make_run_state(self) -> RunState:
        return ColumnRunState(
            rng=self._rng,
            character=self._character,
            column_rooms=self._column_rooms,
            room_weights=self._room_weights,
            min_special_floor=self._min_special_floor,
            branch_prob=self._branch_prob,
        )
