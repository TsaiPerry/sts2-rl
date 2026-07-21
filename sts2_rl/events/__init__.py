"""Events — mirroring STS2's EventModel (src/Core/Models/Events).

The full Act-1 (Overgrowth) event pool, one event per module. See `base.py`
for the Event/EventOption base classes and the headless drive loop; events
act on a `sts2_rl.run.RunState`.

Each event module calls `@register_event`; importing this package imports
them all (pkgutil auto-discovery), binds every event class into the package
namespace, and freezes the catalogue as `ALL_EVENTS`. Build any event with
`make_event("id", run)`. `OVERGROWTH_EVENTS` lists the Act-1 pool in the
source's order (Overgrowth.cs AllEvents); `allowed_events` filters a pool by
each event's IsAllowed gate, mirroring how the map generator fills event
rooms.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from .base import (
    Event,
    EventOption,
    _EVENT_CLASSES,
    make_event,
    register_event,
)

if TYPE_CHECKING:
    from ..run import RunState

# Import every event module so its @register_event decorator runs.
for _module_info in pkgutil.iter_modules(__path__):
    if _module_info.name != "base":
        importlib.import_module(f"{__name__}.{_module_info.name}")

# Freeze the catalogue and bind each event class into the package namespace.
ALL_EVENTS: dict[str, type[Event]] = dict(_EVENT_CLASSES)
globals().update({cls.__name__: cls for cls in ALL_EVENTS.values()})

from .dense_vegetation import DENSE_VEGETATION_EVENT_ENCOUNTER  # noqa: E402
from .punch_off import PUNCH_OFF_EVENT_ENCOUNTER  # noqa: E402
from .the_lantern_key import MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER  # noqa: E402
from ..monsters.fake_merchant import (  # noqa: E402
    FAKE_MERCHANT_EVENT_ENCOUNTER,
)
from ..monsters.glory import (  # noqa: E402
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)

# The Act-1 pool in the source's order (Overgrowth.cs AllEvents).
OVERGROWTH_EVENTS: tuple[str, ...] = (
    "aroma_of_chaos",
    "byrdonis_nest",
    "dense_vegetation",
    "jungle_maze_adventure",
    "luminous_choir",
    "morphic_grove",
    "sapphire_seed",
    "sunken_statue",
    "tablet_of_truth",
    "unrest_site",
    "wellspring",
    "whispering_hollow",
    "wood_carvings",
)

# The Act-2 pool in the source's order (Underdocks.cs AllEvents). Sunken Statue
# is shared with Act 1.
UNDERDOCKS_EVENTS: tuple[str, ...] = (
    "abyssal_baths",
    "drowning_beacon",
    "endless_conveyor",
    "punch_off",
    "spiraling_whirlpool",
    "sunken_statue",
    "sunken_treasury",
    "doors_of_light_and_dark",
    "trash_heap",
    "waterlogged_scriptorium",
)

# The parallel Act-2 "Hive" pool in the source's order (Hive.cs AllEvents).
HIVE_EVENTS: tuple[str, ...] = (
    "amalgamator",
    "bugslayer",
    "colorful_philosophers",
    "colossal_flower",
    "field_of_man_sized_holes",
    "infested_automaton",
    "lost_wisp",
    "spirit_grafter",
    "the_lantern_key",
    "zen_weaver",
)

# The Act-3 "Glory" pool in the source's order (Glory.cs AllEvents).
GLORY_EVENTS: tuple[str, ...] = (
    "battleworn_dummy",
    "grave_of_the_forgotten",
    "hungry_for_mushrooms",
    "reflections",
    "round_tea_party",
    "trial",
    "tinker_time",
)

# The cross-act pool in the source's order (ModelDb.AllSharedEvents, all 18),
# which ActModel.GenerateRooms appends to EVERY act's event queue before the
# shuffle. Each event's own IsAllowed gate is what keeps it out of the acts it
# doesn't belong in (see RoomSet.ensure_next_event_is_valid). crystal_sphere
# and war_historian_repy are pool stubs (is_allowed=False, never surfaced) —
# carried here so the shuffle spans all 18 ids and the UpFront event-shuffle
# draw count/order matches the game (SP2 parity).
SHARED_EVENTS: tuple[str, ...] = (
    "brain_leech",
    "crystal_sphere",
    "doll_room",
    "fake_merchant",
    "potion_courier",
    "ranwid_the_elder",
    "relic_trader",
    "room_full_of_cheese",
    "self_help_book",
    "slippery_bridge",
    "stone_of_all_time",
    "symbiote",
    "tea_master",
    "the_future_of_potions",
    "the_legends_were_true",
    "this_or_that",
    "war_historian_repy",
    "welcome_to_wongos",
)


def allowed_events(
    run: RunState,
    pool: tuple[str, ...] = OVERGROWTH_EVENTS,
) -> list[str]:
    """Event ids from the pool whose IsAllowed gate passes for this run."""
    return [
        event_id for event_id in pool
        if ALL_EVENTS[event_id].is_allowed(run)
    ]


__all__ = [
    "Event",
    "EventOption",
    "make_event",
    "register_event",
    "ALL_EVENTS",
    "OVERGROWTH_EVENTS",
    "UNDERDOCKS_EVENTS",
    "HIVE_EVENTS",
    "GLORY_EVENTS",
    "SHARED_EVENTS",
    "allowed_events",
    "DENSE_VEGETATION_EVENT_ENCOUNTER",
    "PUNCH_OFF_EVENT_ENCOUNTER",
    "MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER",
    "FAKE_MERCHANT_EVENT_ENCOUNTER",
    "BATTLEWORN_DUMMY_SETTING_1",
    "BATTLEWORN_DUMMY_SETTING_2",
    "BATTLEWORN_DUMMY_SETTING_3",
    *sorted(cls.__name__ for cls in ALL_EVENTS.values()),
]
