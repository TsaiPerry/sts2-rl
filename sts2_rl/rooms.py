"""Room resolution — what a map point becomes when you travel onto it.

Ports the room side of the game's map feature:
  - RoomType.cs             → RoomType (same enum values)
  - RoomSet.cs + ActModel.GenerateRooms → RoomSet (the per-act pre-rolled
    encounter/event queues) and ActRooms (the per-act pools)
  - UnknownMapPointOdds.cs  → UnknownOdds (the "?"-node pity roller)
  - RunManager.BuildRoomTypeBlacklist / RollRoomTypeFor →
    build_room_type_blacklist / roll_room_type

Act coverage mirrors the sim: Overgrowth, Underdocks, and Hive have full
encounter pools (weak/normal/elite/boss splits and the EncounterTag values
transcribed from src/Core/Models/Encounters); only Overgrowth has an event
pool, since Acts 2+ events aren't implemented yet — their unknown-node
Event rolls resolve with `event_id=None` and the caller should treat that
as a no-op room. Glory (Act 3) has a map config in actmap.py but no rooms
config (its roster isn't started, per ENEMIES.md).

Deviations from the source, documented per the repo convention: no shared
(cross-act) events, no unlock/epoch gating, no tutorial first-run "?"
overrides, no boss discovery-order override, and no run-level hooks on the
unknown-odds rolls.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from .actmap import MapPointType

if TYPE_CHECKING:
    from .events.base import Event
    from .monsters import Encounter
    from .relics import Relic


class RoomType(IntEnum):
    """RoomType.cs — same member order/values."""

    UNASSIGNED = 0
    MONSTER = 1
    ELITE = 2
    BOSS = 3
    TREASURE = 4
    SHOP = 5
    EVENT = 6
    REST_SITE = 7
    MAP = 8


@dataclass(frozen=True)
class ActRooms:
    """The per-act room pools ActModel.GenerateRooms draws from.

    Keys index the act's ENCOUNTERS registry. `tags` mirrors each source
    encounter's EncounterTag list (encounters sharing a tag never appear
    back-to-back); untagged encounters are simply absent from the dict.
    """

    name: str
    weak_keys: tuple[str, ...]
    normal_keys: tuple[str, ...]
    elite_keys: tuple[str, ...]
    boss_keys: tuple[str, ...]
    tags: dict[str, tuple[str, ...]] = field(default_factory=dict)
    event_pool: tuple[str, ...] = ()

    def encounters(self) -> dict[str, Encounter]:
        """The act's ENCOUNTERS registry (imported lazily)."""
        import importlib

        module = importlib.import_module(f"sts2_rl.monsters.{self.name}")
        return module.ENCOUNTERS


def _overgrowth_rooms() -> ActRooms:
    from .events import OVERGROWTH_EVENTS

    return ActRooms(
        name="overgrowth",
        weak_keys=(
            "nibbits_weak", "slimes_weak", "shrinker_beetle_weak",
            "fuzzy_wurm_weak",
        ),
        normal_keys=(
            "nibbits_normal", "slimes_normal", "inklets_normal",
            "mawler_normal", "cubex_construct", "flyconid", "fogmog",
            "overgrowth_crawlers", "ruby_raiders", "slithering_strangler",
            "snapping_jaxfruit", "vine_shambler",
        ),
        elite_keys=("bygone_effigy", "byrdonis", "phrog_parasite"),
        boss_keys=("ceremonial_beast", "the_kin", "vantom"),
        # EncounterTag values from src/Core/Models/Encounters/*.cs.
        tags={
            "fuzzy_wurm_weak": ("crawler",),
            "nibbits_weak": ("nibbit",),
            "slimes_weak": ("slimes",),
            "shrinker_beetle_weak": ("shrinker",),
            "slimes_normal": ("slimes",),
            "flyconid": ("mushroom", "slimes"),
            "overgrowth_crawlers": ("shrinker", "crawler"),
            "snapping_jaxfruit": ("mushroom",),
        },
        event_pool=OVERGROWTH_EVENTS,
    )


def _underdocks_rooms() -> ActRooms:
    return ActRooms(
        name="underdocks",
        weak_keys=(
            "corpse_slugs_weak", "seapunk_weak", "sludge_spinner",
            "toadpoles",
        ),
        normal_keys=(
            "corpse_slugs_normal", "cultists", "fossil_stalker",
            "gremlin_merc", "haunted_ship", "living_fog", "punch_construct",
            "seapunk_normal", "sewer_clam", "two_tailed_rats",
        ),
        elite_keys=("phantasmal_gardeners", "skulking_colony", "terror_eel"),
        boss_keys=("lagavulin_matriarch", "soul_fysh", "waterfall_giant"),
        tags={
            "corpse_slugs_weak": ("slugs",),
            "corpse_slugs_normal": ("slugs",),
            "seapunk_weak": ("seapunk",),
            "seapunk_normal": ("seapunk",),
        },
        event_pool=(),  # Act-2 events not implemented in the sim yet
    )


def _hive_rooms() -> ActRooms:
    return ActRooms(
        name="hive",
        weak_keys=(
            "bowlbugs_weak", "exoskeletons_weak", "thieving_hopper",
            "tunneler",
        ),
        normal_keys=(
            "bowlbugs_normal", "chompers", "exoskeletons_normal",
            "hunter_killer", "louse_progenitor", "mytes", "ovicopter",
            "slumbering_beetle", "spiny_toad", "the_obscura",
        ),
        elite_keys=("decimillipede", "entomancer", "infested_prisms"),
        boss_keys=("kaiser_crab", "knowledge_demon", "the_insatiable"),
        tags={
            "bowlbugs_weak": ("workers",),
            "bowlbugs_normal": ("workers",),
            "slumbering_beetle": ("workers",),
            "exoskeletons_weak": ("exoskeletons",),
            "exoskeletons_normal": ("exoskeletons",),
            "thieving_hopper": ("thieves",),
            "tunneler": ("burrower",),
            "chompers": ("chomper",),
        },
        event_pool=(),  # Act-2 events not implemented in the sim yet
    )


_ACT_ROOMS_FACTORIES = {
    "overgrowth": _overgrowth_rooms,
    "underdocks": _underdocks_rooms,
    "hive": _hive_rooms,
}


def act_rooms(name: str) -> ActRooms:
    """Room pools for an act. Raises KeyError for acts without a sim
    encounter roster (currently Glory)."""
    if name not in _ACT_ROOMS_FACTORIES:
        raise KeyError(
            f"No room pools for act {name!r} — its encounters aren't in the "
            f"sim yet (available: {sorted(_ACT_ROOMS_FACTORIES)})"
        )
    return _ACT_ROOMS_FACTORIES[name]()


# ── Grab-bag draws (ActModel.AddWithoutRepeatingTags) ────────────────────

def _shares_tags(rooms: ActRooms, a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return bool(set(rooms.tags.get(a, ())) & set(rooms.tags.get(b, ())))


def _add_without_repeating_tags(
    target: list[str], bag: list[str], rooms: ActRooms, rng: random.Random
) -> None:
    """Draw from the bag, avoiding the previous pick's encounter and tags
    when possible (the game falls back to any draw otherwise)."""
    last = target[-1] if target else None
    eligible = [
        key for key in bag
        if key != last and not _shares_tags(rooms, key, last)
    ]
    pick = rng.choice(eligible) if eligible else rng.choice(bag)
    bag.remove(pick)
    target.append(pick)


class RoomSet:
    """RoomSet.cs — the act's pre-rolled room contents.

    Built once per act: an ordered list of `num_rooms` normal encounters
    (the first `num_weak` drawn from the weak pool, the rest from the
    regular pool, never repeating an EncounterTag back-to-back), 15 elite
    encounters the same way, one boss, and the whole event pool shuffled.
    Rooms then consume these lists in order, wrapping around if exhausted.
    """

    MAX_ELITES = 15  # StandardActMap.maxElites

    def __init__(self, rooms: ActRooms, registry: dict[str, Encounter]) -> None:
        self.rooms = rooms
        self.registry = registry
        self.normal_keys: list[str] = []
        self.elite_keys: list[str] = []
        self.event_ids: list[str] = []
        self.boss_key: str = ""
        # DoubleBoss (Asc 10): the second boss on the final act, drawn as a
        # different encounter from the same pool (RoomSet.SecondBoss).
        self.second_boss_key: str | None = None
        self.normal_visited = 0
        self.elite_visited = 0
        self.events_visited = 0
        self.boss_visited = 0

    @classmethod
    def generate(
        cls,
        rooms: ActRooms,
        rng: random.Random,
        num_rooms: int,
        num_weak: int,
        has_second_boss: bool = False,
    ) -> RoomSet:
        """ActModel.GenerateRooms (+ RunManager's DoubleBoss second boss)."""
        room_set = cls(rooms, rooms.encounters())
        room_set.event_ids = list(rooms.event_pool)
        rng.shuffle(room_set.event_ids)
        bag: list[str] = []
        for _ in range(num_weak):
            if not bag:
                bag = list(rooms.weak_keys)
            _add_without_repeating_tags(room_set.normal_keys, bag, rooms, rng)
        bag = []
        for _ in range(num_weak, num_rooms):
            if not bag:
                bag = list(rooms.normal_keys)
            _add_without_repeating_tags(room_set.normal_keys, bag, rooms, rng)
        bag = []
        for _ in range(cls.MAX_ELITES):
            if not bag:
                bag = list(rooms.elite_keys)
            _add_without_repeating_tags(room_set.elite_keys, bag, rooms, rng)
        room_set.boss_key = rng.choice(rooms.boss_keys)
        if has_second_boss:
            # SetSecondBossEncounter: a different boss from the same pool
            # (falls back to the first if the pool has only one).
            others = [k for k in rooms.boss_keys if k != room_set.boss_key]
            room_set.second_boss_key = (
                rng.choice(others) if others else room_set.boss_key
            )
        return room_set

    # ── Next-room accessors (consume with mark_visited) ─────────────────

    @property
    def next_normal_encounter(self) -> Encounter:
        key = self.normal_keys[self.normal_visited % len(self.normal_keys)]
        return self.registry[key]

    @property
    def next_elite_encounter(self) -> Encounter:
        key = self.elite_keys[self.elite_visited % len(self.elite_keys)]
        return self.registry[key]

    @property
    def next_boss_encounter(self) -> Encounter:
        """RoomSet.NextBossEncounter: the second boss once the first has
        been visited (DoubleBoss), otherwise the first."""
        if self.boss_visited != 0 and self.second_boss_key is not None:
            return self.registry[self.second_boss_key]
        return self.registry[self.boss_key]

    @property
    def next_event_id(self) -> str | None:
        if not self.event_ids:
            return None
        return self.event_ids[self.events_visited % len(self.event_ids)]

    def mark_visited(self, room_type: RoomType) -> None:
        if room_type == RoomType.MONSTER:
            self.normal_visited += 1
        elif room_type == RoomType.ELITE:
            self.elite_visited += 1
        elif room_type == RoomType.EVENT:
            self.events_visited += 1
        elif room_type == RoomType.BOSS:
            self.boss_visited += 1

    def ensure_next_event_is_valid(self, run) -> None:
        """RoomSet.EnsureNextEventIsValid: skip events already seen this
        run or whose IsAllowed gate fails; allow repeats when exhausted."""
        if not self.event_ids:
            return
        from .events import ALL_EVENTS

        for _ in range(len(self.event_ids)):
            event_id = self.next_event_id
            if (
                ALL_EVENTS[event_id].is_allowed(run)
                and event_id not in run.visited_event_ids
            ):
                return
            self.events_visited += 1
        # All unique events exhausted; repetition is allowed (source logs
        # a warning here).


class UnknownOdds:
    """UnknownMapPointOdds.cs — the "?"-node pity roller.

    Base odds: Monster 10%, Treasure 2%, Shop 3%, Elite disabled (-1);
    Event is the remainder. Every roll, each type that didn't come up
    gains its base odds again; the rolled type resets to base. Odds reset
    fully between acts.
    """

    BASE_ODDS: dict[RoomType, float] = {
        RoomType.MONSTER: 0.1,
        RoomType.ELITE: -1.0,
        RoomType.TREASURE: 0.02,
        RoomType.SHOP: 0.03,
    }

    def __init__(self) -> None:
        self._base = dict(self.BASE_ODDS)
        self._current = dict(self.BASE_ODDS)

    def odds(self, room_type: RoomType) -> float:
        return self._current[room_type]

    @property
    def event_odds(self) -> float:
        return max(
            0.0, 1.0 - sum(v for v in self._current.values() if v > 0.0)
        )

    def roll(
        self,
        rng: random.Random,
        blacklist: frozenset[RoomType] | set[RoomType] = frozenset(),
    ) -> RoomType:
        allowed = (set(self._current) | {RoomType.EVENT}) - set(blacklist)
        # Fallback if Event itself were blacklisted (never happens today).
        result = (
            RoomType.EVENT if RoomType.EVENT in allowed else min(allowed)
        )
        threshold = rng.random()
        cumulative = 0.0
        for room_type, odds in self._current.items():
            if room_type in allowed and odds >= 0.0:
                cumulative += odds
                if threshold <= cumulative:
                    result = room_type
                    break
        for room_type, base in self._base.items():
            if room_type == result:
                self._current[room_type] = base
            elif room_type in allowed:
                self._current[room_type] += base
        return result

    def reset_to_base(self) -> None:
        self._current = dict(self._base)


def build_room_type_blacklist(
    previous_room_types: list[RoomType],
    next_points,
) -> set[RoomType]:
    """RunManager.BuildRoomTypeBlacklist: no shop from a "?" if the
    previous point already produced a shop, or if every next point is
    a shop anyway."""
    blacklist: set[RoomType] = set()
    next_points = list(next_points)
    if RoomType.SHOP in previous_room_types or (
        next_points
        and all(p.point_type == MapPointType.SHOP for p in next_points)
    ):
        blacklist.add(RoomType.SHOP)
    return blacklist


def roll_room_type(
    point_type: MapPointType,
    unknown_odds: UnknownOdds,
    rng: random.Random,
    blacklist: frozenset[RoomType] | set[RoomType] = frozenset(),
) -> RoomType:
    """RunManager.RollRoomTypeFor: 1:1 mapping except Unknown."""
    mapping = {
        MapPointType.UNASSIGNED: RoomType.UNASSIGNED,
        MapPointType.SHOP: RoomType.SHOP,
        MapPointType.TREASURE: RoomType.TREASURE,
        MapPointType.REST_SITE: RoomType.REST_SITE,
        MapPointType.MONSTER: RoomType.MONSTER,
        MapPointType.ELITE: RoomType.ELITE,
        MapPointType.BOSS: RoomType.BOSS,
        MapPointType.ANCIENT: RoomType.EVENT,
    }
    if point_type == MapPointType.UNKNOWN:
        return unknown_odds.roll(rng, blacklist)
    return mapping[point_type]


@dataclass
class RoomResolution:
    """What entering a map point produced. The caller drives the room:
    combats via RunState.create_combat(resolution.encounter), events via
    resolution.event, rest sites via the RunState heal/upgrade helpers.
    """

    point: "object"  # MapPoint (kept untyped to avoid a circular import)
    map_point_type: MapPointType
    room_type: RoomType
    encounter: Encounter | None = None
    event: Event | None = None
    relic: Relic | None = None
