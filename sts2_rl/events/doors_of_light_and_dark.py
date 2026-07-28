from __future__ import annotations

_CARDS = 2  # CardsVar(2)

from ..actmap import stable_shuffle
from ..player import _compare_to_key
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
        # `Deck.Where(IsUpgradable).ToList().StableShuffle(base.Rng).Take(2)`
        # (DoorsOfLightAndDark.cs:28-29): the sort (CardModel.CompareTo — the
        # UPPERCASE ModelId entry, then the upgrade level) makes the pick
        # independent of the deck's incidental order, and the shuffle runs on
        # the event's own Rng.
        er = self.event_rng
        chosen = stable_shuffle(
            list(upgradable), er if er is not None else self.rng,
            key=_compare_to_key)[:count]
        for card in chosen:
            card.upgrade()
        self._finish("LIGHT")

    def _dark(self) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), 1)
        self.run.remove_cards(chosen)
        self._finish("DARK")
