"""Crystal Sphere (Models/Events/CrystalSphere.cs) — pool stub.

Deferred by decision (docs/superpowers/plans/2026-07-19-shared-events.md): the
whole payout is the 11x11 reveal minigame (Events/Custom/CrystalSphereEvent/),
which has no faithful headless analogue. It is registered here only so it
occupies its slot in ``ModelDb.AllSharedEvents`` — the game shuffles the full
18-event shared pool onto every act's queue, so the sim must carry the same 18
ids for the UpFront event-shuffle draw count/order to match (SP2).

Its game gate is ``acts 2-3 && all players' gold >= 100``; here ``is_allowed``
returns False so the un-portable minigame is never surfaced (same treatment as
the other deferred shared event, [war_historian_repy]). is_allowed consumes no
RNG, so this does not affect any parity counter.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


@register_event
class CrystalSphere(Event):
    id = "crystal_sphere"
    name = "Crystal Sphere"

    @classmethod
    def is_allowed(cls, run: "RunState") -> bool:
        # Deferred (minigame not ported); never eligible in the sim.
        return False

    def initial_options(self) -> list[EventOption]:
        # Unreachable (is_allowed is False); finish immediately if ever begun.
        return []
