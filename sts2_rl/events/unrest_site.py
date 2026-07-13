from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MAX_HP_LOSS = 8  # DynamicVar("MaxHpLoss", 8)


@register_event
class UnrestSite(Event):
    """Unrest Site — a cursed full heal, or max HP for a relic.

    Source: UnrestSite.cs
      IsAllowed: current HP <= 70% of max HP
      CalculateVars: Heal = missing HP
      REST: heal to full, add a Poor Sleep curse to the deck
      KILL: lose 8 max HP, obtain the next grab-bag relic
    """

    id = "unrest_site"
    name = "Unrest Site"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.hp <= run.max_hp * 0.70

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("REST", self._rest),
            EventOption("KILL", self._kill),
        ]

    def _rest(self) -> None:
        self.run.heal(self.run.max_hp - self.run.hp)
        self.run.add_card(make_card("poor_sleep"))
        self._finish("REST")

    def _kill(self) -> None:
        self.run.lose_max_hp(_MAX_HP_LOSS)
        self.run.obtain_relic_from_grab_bag()
        self._finish("KILL")
