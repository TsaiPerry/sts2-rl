from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from ..enchantments import SoulsEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


def _has_enchantable(run: RunState) -> bool:
    return any(SoulsEnchantment.can_enchant(c) for c in run.deck)


@register_event
class GraveOfTheForgotten(Event):
    """Grave of the Forgotten — enchant a card with Souls (and take a Decay), or
    accept the Forgotten Soul relic.

    Source: GraveOfTheForgotten.cs
      IsAllowed: the deck has a card Souls can enchant (a card with Exhaust)
      CONFRONT: add a Decay curse, then enchant 1 chosen Exhaust card with Souls
                (which removes its Exhaust); locked if no such card remains
      ACCEPT:   obtain the Forgotten Soul relic
    """

    id = "grave_of_the_forgotten"
    name = "Grave of the Forgotten"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return _has_enchantable(run)

    def initial_options(self) -> list[EventOption]:
        if _has_enchantable(self.run):
            confront = EventOption("CONFRONT", self._confront)
        else:
            confront = EventOption("CONFRONT_LOCKED", None)
        return [confront, EventOption("ACCEPT", self._accept)]

    def _confront(self) -> None:
        self.run.add_card(make_card("decay"))
        candidates = [c for c in self.run.deck if SoulsEnchantment.can_enchant(c)]
        for card in self.run.select_cards("enchant", candidates, 1):
            make_enchantment("souls").attach(card)
        self._finish("CONFRONT")

    def _accept(self) -> None:
        self.run.add_relic("forgotten_soul")
        self._finish("ACCEPT")
