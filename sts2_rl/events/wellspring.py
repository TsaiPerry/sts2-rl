from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event

_BATHE_CURSES = 1  # DynamicVar("BatheCurses", 1)


@register_event
class Wellspring(Event):
    """Wellspring — bottle the water for a potion, or bathe in it.

    Source: Wellspring.cs
      BOTTLE: a random potion from the potion pools is offered as a reward
      BATHE:  remove 1 chosen card, add a Guilty curse to the deck
    """

    id = "wellspring"
    name = "Wellspring"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("BOTTLE", self._bottle),
            EventOption("BATHE", self._bathe),
        ]

    def _bottle(self) -> None:
        # RewardsCmd.OfferCustom(PotionReward): headlessly, the potion is
        # kept when a slot is free and skipped otherwise.
        self.run.add_potion(self.run.random_potion())
        self._finish("BOTTLE")

    def _bathe(self) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), 1)
        self.run.remove_cards(chosen)
        for _ in range(_BATHE_CURSES):
            self.run.add_card(make_card("guilty"))
        self._finish("BATHE")
