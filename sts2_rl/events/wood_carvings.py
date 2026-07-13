from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity, make_card
from ..enchantments import SlitherEnchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..cards import Card
    from ..run import RunState


@register_event
class WoodCarvings(Event):
    """Wood Carvings — reshape a Basic card, or enchant a card with Slither.

    Source: WoodCarvings.cs
      IsAllowed: the deck has a removable Basic-rarity card
      BIRD:  choose 1 transformable Basic card; it becomes Peck
      SNAKE: choose 1 eligible card; it gains the Slither enchantment
             (cost becomes random 0-3 whenever drawn) — locked when no card
             can be enchanted
      TORUS: choose 1 transformable Basic card; it becomes Toric Toughness
    """

    id = "wood_carvings"
    name = "Wood Carvings"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return any(
            c.rarity == CardRarity.BASIC and not c.eternal for c in run.deck
        )

    def _basic_candidates(self) -> list[Card]:
        return [
            c for c in self.run.transformable_cards()
            if c.rarity == CardRarity.BASIC
        ]

    def initial_options(self) -> list[EventOption]:
        snake_candidates = [
            c for c in self.run.deck if SlitherEnchantment.can_enchant(c)
        ]
        snake = (
            EventOption("SNAKE", self._snake)
            if snake_candidates
            else EventOption("SNAKE_LOCKED", None)
        )
        return [
            EventOption("BIRD", self._bird),
            snake,
            EventOption("TORUS", self._torus),
        ]

    def _bird(self) -> None:
        chosen = self.run.select_cards("transform", self._basic_candidates(), 1)
        if chosen:
            self.run.transform_card(chosen[0], into=make_card("peck"))
        self._finish("BIRD")

    def _snake(self) -> None:
        candidates = [c for c in self.run.deck if SlitherEnchantment.can_enchant(c)]
        chosen = self.run.select_cards("enchant", candidates, 1)
        if chosen:
            SlitherEnchantment().attach(chosen[0])
        self._finish("SNAKE")

    def _torus(self) -> None:
        chosen = self.run.select_cards("transform", self._basic_candidates(), 1)
        if chosen:
            self.run.transform_card(chosen[0], into=make_card("toric_toughness"))
        self._finish("TORUS")
