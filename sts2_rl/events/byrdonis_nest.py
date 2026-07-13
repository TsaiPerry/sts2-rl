from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MAX_HP_GAIN = 7  # MaxHpVar(7)


@register_event
class ByrdonisNest(Event):
    """Byrdonis Nest — eat the egg for max HP, or take it into your deck.

    Source: ByrdonisNest.cs
      EAT:  gain 7 max HP
      TAKE: add a Byrdonis Egg (Unplayable Quest card) to the deck
      IsAllowed: no player has an event pet (a pet relic or a Byrdonis Egg
      in the deck — Player.HasEventPet)
    """

    id = "byrdonis_nest"
    name = "Byrdonis Nest"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        if any(card.id == "byrdonis_egg" for card in run.deck):
            return False
        return not any(getattr(relic, "adds_pet", False) for relic in run.relics)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("EAT", self._eat),
            EventOption("TAKE", self._take),
        ]

    def _eat(self) -> None:
        self.run.gain_max_hp(_MAX_HP_GAIN)
        self._finish("EAT")

    def _take(self) -> None:
        self.run.add_card(make_card("byrdonis_egg"))
        self._finish("TAKE")
