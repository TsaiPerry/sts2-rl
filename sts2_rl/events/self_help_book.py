from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardType
from ..enchantments import make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..cards import Card
    from ..run import RunState

_AMOUNT = 2   # Enchantment{1,2,3}Amount

# (option key, enchantment id, the card type the selection is restricted to).
_CHOICES = (
    ("READ_THE_BACK", "sharp", CardType.ATTACK),
    ("READ_PASSAGE", "nimble", CardType.SKILL),
    ("READ_ENTIRE_BOOK", "swift", CardType.POWER),
)


@register_event
class SelfHelpBook(Event):
    """Self Help Book — enchant an Attack, a Skill, or a Power.

    Shared event (ModelDb.AllSharedEvents). Source: SelfHelpBook.cs
      READ_THE_BACK:     Sharp 2 on a chosen Attack
      READ_PASSAGE:      Nimble 2 on a chosen Skill
      READ_ENTIRE_BOOK:  Swift 2 on a chosen Power
    Each option locks (a null onChosen) when the deck holds no card of that
    type the enchantment can take; when all three lock, the event instead
    offers the single NO_OPTIONS exit.
    """

    id = "self_help_book"
    name = "Self Help Book"

    def _candidates(self, enchantment_id: str, card_type: CardType) -> list[Card]:
        """DeckFilter: a deck card of this type the enchantment can take."""
        cls = type(make_enchantment(enchantment_id))
        return [
            c for c in self.run.deck
            if c.card_type == card_type and cls.can_enchant(c)
        ]

    def initial_options(self) -> list[EventOption]:
        available = {
            key: self._candidates(eid, card_type)
            for key, eid, card_type in _CHOICES
        }
        if not any(available.values()):
            return [EventOption("NO_OPTIONS", lambda: self._finish("NO_OPTIONS"))]
        options = []
        for key, eid, card_type in _CHOICES:
            if available[key]:
                options.append(EventOption(
                    key,
                    lambda k=key, e=eid, t=card_type: self._enchant(k, e, t),
                ))
            else:
                options.append(EventOption(f"{key}_LOCKED", None))
        return options

    def _enchant(self, key: str, enchantment_id: str, card_type: CardType) -> None:
        chosen = self.run.select_cards(
            "enchant", self._candidates(enchantment_id, card_type), 1)
        for card in chosen:
            enchantment = make_enchantment(enchantment_id)
            enchantment.amount = _AMOUNT
            enchantment.attach(card)
        self._finish(key)
