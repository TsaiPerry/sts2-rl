"""Room resolution — what a map point becomes when you travel onto it.

Ports the room side of the game's map feature:
  - RoomType.cs             → RoomType (same enum values)
  - RoomSet.cs + ActModel.GenerateRooms → RoomSet (the per-act pre-rolled
    encounter/event queues) and ActRooms (the per-act pools)
  - UnknownMapPointOdds.cs  → UnknownOdds (the "?"-node pity roller)
  - RunManager.BuildRoomTypeBlacklist / RollRoomTypeFor →
    build_room_type_blacklist / roll_room_type

Act coverage mirrors the sim: Overgrowth, Underdocks, Hive, and Glory all
have full encounter pools (weak/normal/elite/boss splits and the EncounterTag
values transcribed from src/Core/Models/Encounters) and full event pools
(each act's AllEvents order, events/__init__.py) plus the cross-act
SHARED_EVENTS pool every act's queue carries — every act ModelDb ships is
wired into the run layer.

Deviations from the source, documented per the repo convention: no
unlock/epoch gating, no tutorial first-run "?" overrides, no boss
discovery-order override, and no run-level hooks on the unknown-odds rolls.
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
        # Game order: AllEncounters (Overgrowth.GenerateAllEncounters,
        # alphabetical-by-class) filtered by RoomType/IsWeak. The first-run
        # ApplyActDiscoveryOrderModifications swap order is deliberately NOT
        # used (tutorial mods are off for real runs — see the module docstring).
        weak_keys=(
            "fuzzy_wurm_weak", "nibbits_weak", "shrinker_beetle_weak",
            "slimes_weak",
        ),
        normal_keys=(
            "cubex_construct", "flyconid", "fogmog", "inklets_normal",
            "mawler_normal", "nibbits_normal", "overgrowth_crawlers",
            "ruby_raiders", "slimes_normal", "slithering_strangler",
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
    from .events import UNDERDOCKS_EVENTS

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
        event_pool=UNDERDOCKS_EVENTS,
    )


def _hive_rooms() -> ActRooms:
    from .events import HIVE_EVENTS

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
        event_pool=HIVE_EVENTS,
    )


def _glory_rooms() -> ActRooms:
    from .events import GLORY_EVENTS

    return ActRooms(
        name="glory",
        weak_keys=(
            "devoted_sculptor", "scrolls_of_biting_weak", "turret_operator",
        ),
        normal_keys=(
            "axebots", "construct_menagerie", "fabricator", "frog_knight",
            "globe_head", "owl_magistrate", "scrolls_of_biting_normal",
            "slimed_berserker", "the_lost_and_forgotten",
        ),
        elite_keys=("knights", "mecha_knight", "soul_nexus"),
        boss_keys=("aeonglass", "queen", "test_subject"),
        # EncounterTag values from src/Core/Models/Encounters/*.cs: the two
        # Scrolls of Biting variants share EncounterTag.Scrolls, Knights carries
        # EncounterTag.Knights (everything else is untagged).
        tags={
            "scrolls_of_biting_weak": ("scrolls",),
            "scrolls_of_biting_normal": ("scrolls",),
            "knights": ("knights",),
        },
        event_pool=GLORY_EVENTS,
    )


_ACT_ROOMS_FACTORIES = {
    "overgrowth": _overgrowth_rooms,
    "underdocks": _underdocks_rooms,
    "hive": _hive_rooms,
    "glory": _glory_rooms,
}


def act_has_rooms(name: str) -> bool:
    """Whether the act's encounter roster is ported (all four ModelDb acts
    are); RunState.start_run trims its default act list with this."""
    return name in _ACT_ROOMS_FACTORIES


def act_rooms(name: str) -> ActRooms:
    """Room pools for an act. Raises KeyError for acts without a sim
    encounter roster."""
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
        # The Ancient shrine this act rolls (ActModel.GenerateRooms:
        # `NextItem(GetUnlockedAncients ∪ sharedAncientSubset)`). Only the
        # parity path fills it — the legacy path rolls ancients in the driver.
        self.ancient_key: str | None = None
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
        rng,
        num_rooms: int,
        num_weak: int,
        has_second_boss: bool = False,
        ancient_pool: tuple[str, ...] = (),
    ) -> RoomSet:
        """ActModel.GenerateRooms (+ RunManager's DoubleBoss second boss).

        Two draw models share the event-pool shuffle but split on the encounter
        grab. A game ``Rng`` (SP2 parity path, `rng_set.up_front`) reproduces
        the run.save room lists via ``GrabBag.GrabAndRemove``'s reject-and-redraw
        and ``NextItem`` boss/ancient rolls, consuming exactly the game's
        ``UpFront`` draw count. A legacy ``random.Random`` keeps the pre-SP2
        single-``choice`` behavior (its non-faithful draw count is irrelevant to
        RL training and untouched here). ``ancient_pool`` (parity only) is the
        act's ``GetUnlockedAncients ∪ sharedAncientSubset`` — see
        RunManager.GenerateRooms."""
        from .events import SHARED_EVENTS
        from .rng import Rng

        room_set = cls(rooms, rooms.encounters())
        # AllEvents.Concat(ModelDb.AllSharedEvents), then shuffle: the shared
        # (cross-act) pool rides every act's queue, and each shared event's
        # own IsAllowed gate — applied by ensure_next_event_is_valid — is what
        # keeps it out of the acts it doesn't belong in.
        room_set.event_ids = list(rooms.event_pool) + list(SHARED_EVENTS)
        rng.shuffle(room_set.event_ids)
        if isinstance(rng, Rng):
            room_set._generate_parity(rng, num_rooms, num_weak, ancient_pool)
        else:
            room_set._generate_legacy(
                rng, num_rooms, num_weak, has_second_boss
            )
        return room_set

    def _generate_parity(
        self, rng, num_rooms: int, num_weak: int,
        ancient_pool: tuple[str, ...],
    ) -> None:
        """ActModel.GenerateRooms on a game ``Rng`` (`UpFront`): faithful
        ``GrabBag.GrabAndRemove`` rejection draws for encounters and ``NextItem``
        boss/ancient rolls. The DoubleBoss second boss is a separate post-pass
        in RunManager.GenerateRooms, not part of this method, so it is not
        rolled here."""
        rooms = self.rooms
        bag: list[str] = []
        for _ in range(num_weak):
            if not bag:
                bag = list(rooms.weak_keys)
            self._grab_without_repeating_tags(self.normal_keys, bag, rng)
        bag = []
        for _ in range(num_weak, num_rooms):
            if not bag:
                bag = list(rooms.normal_keys)
            self._grab_without_repeating_tags(self.normal_keys, bag, rng)
        bag = []
        for _ in range(self.MAX_ELITES):
            if not bag:
                bag = list(rooms.elite_keys)
            self._grab_without_repeating_tags(self.elite_keys, bag, rng)
        self.boss_key = rng.next_item(list(rooms.boss_keys))
        if ancient_pool:
            self.ancient_key = rng.next_item(list(ancient_pool))

    def _grab_without_repeating_tags(
        self, target: list[str], bag: list[str], rng,
    ) -> None:
        """ActModel.AddWithoutRepeatingTags: grab a tag-safe, non-repeat pick
        from the bag; if the predicate excludes everything, fall back to any
        grab (both via GrabBag.GrabAndRemove's rejection model)."""
        from .rng import grab_and_remove

        last = target[-1] if target else None
        pick = grab_and_remove(
            bag, rng,
            lambda k: k != last and not _shares_tags(self.rooms, k, last),
        )
        if pick is None:
            pick = grab_and_remove(bag, rng)
        if pick is not None:
            target.append(pick)

    def _generate_legacy(
        self, rng: random.Random, num_rooms: int, num_weak: int,
        has_second_boss: bool,
    ) -> None:
        """Pre-SP2 room generation on a shared ``random.Random`` (RL path)."""
        rooms = self.rooms
        bag: list[str] = []
        for _ in range(num_weak):
            if not bag:
                bag = list(rooms.weak_keys)
            _add_without_repeating_tags(self.normal_keys, bag, rooms, rng)
        bag = []
        for _ in range(num_weak, num_rooms):
            if not bag:
                bag = list(rooms.normal_keys)
            _add_without_repeating_tags(self.normal_keys, bag, rooms, rng)
        bag = []
        for _ in range(self.MAX_ELITES):
            if not bag:
                bag = list(rooms.elite_keys)
            _add_without_repeating_tags(self.elite_keys, bag, rooms, rng)
        self.boss_key = rng.choice(rooms.boss_keys)
        if has_second_boss:
            # SetSecondBossEncounter: a different boss from the same pool
            # (falls back to the first if the pool has only one).
            others = [k for k in rooms.boss_keys if k != self.boss_key]
            self.second_boss_key = (
                rng.choice(others) if others else self.boss_key
            )

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
        allowed_room_types: frozenset[RoomType] | set[RoomType] | None = None,
    ) -> RoomType:
        # `allowed_room_types` is the set surviving ModifyUnknownMapPointRoomTypes
        # (Golden Compass narrows it to {Event}); None = the default full set.
        if allowed_room_types is None:
            allowed = (set(self._current) | {RoomType.EVENT}) - set(blacklist)
        else:
            allowed = set(allowed_room_types) - set(blacklist)
        # Fallback if Event itself were blacklisted (never happens today).
        result = (
            RoomType.EVENT
            if RoomType.EVENT in allowed or not allowed
            else min(allowed)
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
    allowed_room_types: frozenset[RoomType] | set[RoomType] | None = None,
) -> RoomType:
    """RunManager.RollRoomTypeFor: 1:1 mapping except Unknown.

    `allowed_room_types` (the set after ModifyUnknownMapPointRoomTypes) only
    affects "?" nodes — Golden Compass passes {Event} to force events.
    """
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
        return unknown_odds.roll(rng, blacklist, allowed_room_types)
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
    # Shop rooms carry a stocked MerchantInventory to buy from (shop.py).
    shop: "object | None" = None
    # Gold granted by the room itself (Spoils Map's treasure quest payout).
    gold: int = 0
