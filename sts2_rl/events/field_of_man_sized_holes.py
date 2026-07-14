from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from ..enchantments import PerfectFitEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_CARDS = 2  # CardsVar(2)


@register_event
class FieldOfManSizedHoles(Event):
    """Field of Man-Sized Holes — resist (remove 2 cards, gain a Normality
    curse), or enter your hole (enchant a card with Perfect Fit).

    Source: FieldOfManSizedHoles.cs
      IsAllowed: the deck has a card Perfect Fit can enchant
      RESIST:         remove 2 chosen cards, add a Normality curse
      ENTER_YOUR_HOLE: enchant 1 chosen card with Perfect Fit
    """

    id = "field_of_man_sized_holes"
    name = "Field of Man-Sized Holes"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return any(PerfectFitEnchantment.can_enchant(c) for c in run.deck)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("RESIST", self._resist),
            EventOption("ENTER_YOUR_HOLE", self._enter_your_hole),
        ]

    def _resist(self) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), _CARDS)
        self.run.remove_cards(chosen)
        self.run.add_card(make_card("normality"))
        self._finish("RESIST")

    def _enter_your_hole(self) -> None:
        candidates = [c for c in self.run.deck if PerfectFitEnchantment.can_enchant(c)]
        for card in self.run.select_cards("enchant", candidates, 1):
            make_enchantment("perfect_fit").attach(card)
        self._finish("ENTER_YOUR_HOLE")
