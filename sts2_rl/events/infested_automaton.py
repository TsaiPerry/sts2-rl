from __future__ import annotations

from ..cards import CardType, make_card
from ..cards.pool import pool_card_ids, random_pool_cards
from .base import Event, EventOption, register_event


@register_event
class InfestedAutomaton(Event):
    """Infested Automaton — study it for a Power card, or touch its core for a
    random 0-cost card.

    Source: InfestedAutomaton.cs
      STUDY:      add a random Power card from the character pool
      TOUCH_CORE: add a random 0-cost (non-X) card from the character pool
    """

    id = "infested_automaton"
    name = "Infested Automaton"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("STUDY", self._study),
            EventOption("TOUCH_CORE", self._touch_core),
        ]

    def _study(self) -> None:
        for card in random_pool_cards(self.rng, 1, CardType.POWER):
            self.run.add_card(card)
        self._finish("STUDY")

    def _touch_core(self) -> None:
        candidates = [
            cid for cid in pool_card_ids()
            if make_card(cid).energy_cost == 0 and not make_card(cid).energy_cost_x
        ]
        if candidates:
            self.run.add_card(make_card(self.rng.choice(candidates)))
        self._finish("TOUCH_CORE")
