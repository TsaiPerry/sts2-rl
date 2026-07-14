from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BREATHING_COST = 50     # DynamicVar("BreathingTechniquesCost", 50)
_EMOTIONAL_COST = 125    # DynamicVar("EmotionalAwarenessCost", 125)
_ARACHNID_COST = 250     # DynamicVar("ArachnidAcupunctureCost", 250)


@register_event
class ZenWeaver(Event):
    """Zen Weaver — buy Enlightenment cards, or pay to remove cards.

    Source: ZenWeaver.cs
      IsAllowed: gold >= 125
      BREATHING_TECHNIQUES: pay 50 gold, add 2 Enlightenment cards
      EMOTIONAL_AWARENESS:  pay 125 gold, remove 1 chosen card (locked < 125)
      ARACHNID_ACUPUNCTURE: pay 250 gold, remove 2 chosen cards (locked < 250)
    """

    id = "zen_weaver"
    name = "Zen Weaver"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _EMOTIONAL_COST

    def initial_options(self) -> list[EventOption]:
        options = [EventOption("BREATHING_TECHNIQUES", self._breathing_techniques)]
        if self.run.gold >= _EMOTIONAL_COST:
            options.append(EventOption("EMOTIONAL_AWARENESS", self._emotional_awareness))
        else:
            options.append(EventOption("LOCKED", None))
        if self.run.gold >= _ARACHNID_COST:
            options.append(EventOption("ARACHNID_ACUPUNCTURE", self._arachnid_acupuncture))
        else:
            options.append(EventOption("LOCKED", None))
        return options

    def _breathing_techniques(self) -> None:
        self.run.lose_gold(_BREATHING_COST)
        for _ in range(2):
            self.run.add_card(make_card("enlightenment"))
        self._finish("BREATHING_TECHNIQUES")

    def _remove_and_pay(self, cost: int, count: int) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), count)
        self.run.remove_cards(chosen)
        self.run.lose_gold(cost)

    def _emotional_awareness(self) -> None:
        self._remove_and_pay(_EMOTIONAL_COST, 1)
        self._finish("EMOTIONAL_AWARENESS")

    def _arachnid_acupuncture(self) -> None:
        self._remove_and_pay(_ARACHNID_COST, 2)
        self._finish("ARACHNID_ACUPUNCTURE")
