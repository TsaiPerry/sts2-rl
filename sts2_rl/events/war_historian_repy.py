"""War Historian Repy (Models/Events/WarHistorianRepy.cs) — pool stub.

``IsAllowed => false`` in the source: the room is reached only by carrying a
Lantern Key card into it via a quest/room hook the sim does not model
(docs/superpowers/plans/2026-07-19-shared-events.md). Registered here only so
it occupies its slot in ``ModelDb.AllSharedEvents`` — the game shuffles the
full 18-event shared pool onto every act's queue, so the sim must carry the
same 18 ids for the UpFront event-shuffle draw count/order to match (SP2).

``is_allowed`` mirrors the source (always False) and consumes no RNG, so this
does not affect any parity counter. See [crystal_sphere], the other deferred
shared event.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


@register_event
class WarHistorianRepy(Event):
    id = "war_historian_repy"
    name = "War Historian Repy"

    @classmethod
    def is_allowed(cls, run: "RunState") -> bool:
        # WarHistorianRepy.IsAllowed => false (Lantern-Key room hook unmodeled).
        return False

    def initial_options(self) -> list[EventOption]:
        # Unreachable (is_allowed is False); finish immediately if ever begun.
        return []
