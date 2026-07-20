from __future__ import annotations

from typing import TYPE_CHECKING

from ..enchantments import CorruptedEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_TRANSFORM_COUNT = 1   # CardsVar(1)


@register_event
class Symbiote(Event):
    """Symbiote — let it corrupt a card, or burn it away.

    Shared event (ModelDb.AllSharedEvents). Source: Symbiote.cs
      IsAllowed: acts 2-3 (CurrentActIndex > 0)
      APPROACH:       enchant a chosen card with Corrupted (locked when no
                      card can take it — Corrupted is Attack-only)
      KILL_WITH_FIRE: transform 1 chosen card
    """

    id = "symbiote"
    name = "Symbiote"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index > 0

    def _corrupt_candidates(self) -> list:
        return [c for c in self.run.deck if CorruptedEnchantment.can_enchant(c)]

    def initial_options(self) -> list[EventOption]:
        approach = (
            EventOption("APPROACH", self._approach)
            if self._corrupt_candidates()
            else EventOption("APPROACH_LOCKED", None)
        )
        return [approach, EventOption("KILL_WITH_FIRE", self._kill_with_fire)]

    def _approach(self) -> None:
        for card in self.run.select_cards("enchant", self._corrupt_candidates(), 1):
            make_enchantment("corrupted").attach(card)
        self._finish("APPROACH")

    def _kill_with_fire(self) -> None:
        chosen = self.run.select_cards(
            "transform", self.run.transformable_cards(), _TRANSFORM_COUNT)
        for card in chosen:
            self.run.transform_card(card)
        self._finish("KILL_WITH_FIRE")
