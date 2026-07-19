"""STS2CurriculumRunEnv — the phase-1 curriculum env: a full run on a
randomized single-column map, rewarded by floors reached and nothing else.

The training plan this implements (see RL.md for the base env's design):

  1. **Floor-only reward.** Floors reached is the one metric that actually
     measures how well a run is going, and the one that can't be reward-
     hacked. Per-step reward is `floor_reward` × floors gained (0 or 1),
     plus a terminal `reward_win` worth a few floors so beating the final
     boss is honestly weighted against dying to it. There is NO HP-delta
     term: the critic learns "low HP → fewer future floors" on its own from
     the observation, which densifies the signal through GAE without
     biasing the optimal policy the way hand-coded HP shaping does.
     Because that internalization has to propagate across hundreds of
     steps, train this env with γ≈0.999 (train_torch.py defaults to that
     for --env column).

  2. **Randomized single-column maps.** Every act's map is one column
     ending at the boss (the GoldenPathActMap shape), as long as the act's
     real room count (`column_rooms` overrides it), but the room-type
     sequence is re-sampled every act from `room_weights`, monster-heavy
     by default. One column means routing
     can never dodge a fight (a bad early policy can't learn risk-averse
     pathing instead of combat); re-sampling means the schedule can't be
     memorized — the only way to prepare for "elite next floor" is to read
     the map-lookahead observation, which is exactly the skill that
     transfers to the real branching maps. "?" floors always resolve to
     Events (Golden Compass semantics), so the sampled combat count is the
     actual combat count.

Phase 2 is the unmodified STS2RunEnv, whose reward defaults are these same
floor-only settings: the observation/action layout here is IDENTICAL (this
class only overrides the RunState factory), so a checkpoint trained here
resumes directly on --env run. Prefer annealing — mix real maps in gradually — over
a hard swap, since map *choices* never occur on a single column (the MAP
decision each floor has exactly one option).

The column obeys StandardActMap's placement rules exactly as they project
onto a single path: forced rows (row 1 Monster, row `n_rooms − 6` Treasure,
top row Rest), no Elite/Rest below row 6, no Rest in the top 3 rows, and no
special room (elite/rest/treasure/shop) on consecutive floors — the same
restriction sets actmap.py uses. What stays deliberately non-faithful (it
is a training curriculum, not a fidelity port): type *frequencies* come
from `room_weights` instead of the per-map queue counts (the defaults are
calibrated to the measured real-map mix), and the map-modifier relic/card
pipeline (Spoils Map, Golden Compass regeneration) is skipped — the column
IS the map.
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
    ) -> None:
        super().__init__(rng=rng)
        self._column_rooms = column_rooms
        self._room_weights = room_weights
        self._min_special_floor = min_special_floor

    def _generate_map(self):
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
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._column_rooms = column_rooms
        self._room_weights = dict(room_weights) if room_weights is not None else None
        self._min_special_floor = min_special_floor

    def _make_run_state(self) -> RunState:
        return ColumnRunState(
            rng=self._rng,
            column_rooms=self._column_rooms,
            room_weights=self._room_weights,
            min_special_floor=self._min_special_floor,
        )
