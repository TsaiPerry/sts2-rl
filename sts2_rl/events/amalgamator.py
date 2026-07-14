from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import Card, CardRarity, make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


def _is_valid(tag: str, card: Card) -> bool:
    """Amalgamator.IsValid: a removable Basic card carrying the given tag."""
    return tag in card.tags and card.rarity == CardRarity.BASIC and not card.eternal


@register_event
class Amalgamator(Event):
    """Amalgamator — fuse two Strikes into an Ultimate Strike, or two Defends
    into an Ultimate Defend.

    Source: Amalgamator.cs
      IsAllowed: at least 2 removable Basic Strikes and 2 removable Basic
                 Defends in the deck
      COMBINE_STRIKES: remove 2 chosen Basic Strikes, add an Ultimate Strike
      COMBINE_DEFENDS: remove 2 chosen Basic Defends, add an Ultimate Defend
    """

    id = "amalgamator"
    name = "Amalgamator"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        strikes = sum(1 for c in run.deck if _is_valid("strike", c))
        defends = sum(1 for c in run.deck if _is_valid("defend", c))
        return strikes >= 2 and defends >= 2

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("COMBINE_STRIKES", self._combine_strikes),
            EventOption("COMBINE_DEFENDS", self._combine_defends),
        ]

    def _combine(self, tag: str, result_id: str, page: str) -> None:
        candidates = [c for c in self.run.deck if _is_valid(tag, c)]
        chosen = self.run.select_cards("remove", candidates, 2)
        self.run.remove_cards(chosen)
        self.run.add_card(make_card(result_id))
        self._finish(page)

    def _combine_strikes(self) -> None:
        self._combine("strike", "ultimate_strike", "COMBINE_STRIKES")

    def _combine_defends(self) -> None:
        self._combine("defend", "ultimate_defend", "COMBINE_DEFENDS")
