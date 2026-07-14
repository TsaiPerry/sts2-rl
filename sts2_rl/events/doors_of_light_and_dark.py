from __future__ import annotations

_CARDS = 2  # CardsVar(2)

from .base import Event, EventOption, register_event


@register_event
class DoorsOfLightAndDark(Event):
    """Doors of Light and Dark — upgrade 2 random cards, or remove 1.

    Source: DoorsOfLightAndDark.cs
      LIGHT: upgrade up to 2 random upgradable cards in the deck
      DARK:  remove 1 chosen card
    """

    id = "doors_of_light_and_dark"
    name = "Doors of Light and Dark"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("LIGHT", self._light),
            EventOption("DARK", self._dark),
        ]

    def _light(self) -> None:
        upgradable = self.run.upgradable_cards()
        count = min(_CARDS, len(upgradable))
        for card in self.rng.sample(upgradable, count):
            card.upgrade()
        self._finish("LIGHT")

    def _dark(self) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), 1)
        self.run.remove_cards(chosen)
        self._finish("DARK")
