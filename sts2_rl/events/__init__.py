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
    "allowed_events",
    "DENSE_VEGETATION_EVENT_ENCOUNTER",
    *sorted(cls.__name__ for cls in ALL_EVENTS.values()),
]
