from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


@register_event
class ColorfulPhilosophers(Event):
    """Colorful Philosophers — pick another character's colour and get a card
    reward from its pool.

    Source: ColorfulPhilosophers.cs
      IsAllowed: the player has more than one character card pool unlocked
      Each option offers Common/Uncommon/Rare card rewards from another colour.

    The sim models a single character (Ironclad), so there are no other colour
    pools: IsAllowed is always False and the event presents no options. It is
    registered for pool completeness (Hive.cs AllEvents).
    """

    id = "colorful_philosophers"
    name = "Colorful Philosophers"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        # p.UnlockState.CharacterCardPools.Count() > 1 — never true in the
        # single-character sim.
        return False

    def initial_options(self) -> list[EventOption]:
        # No other-colour pools exist in the sim, so no options are generated
        # (the event finishes immediately if ever entered).
        return []
