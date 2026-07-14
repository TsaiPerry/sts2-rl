from __future__ import annotations

from typing import TYPE_CHECKING

from ..enchantments import SpiralEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


@register_event
class SpiralingWhirlpool(Event):
    """Spiraling Whirlpool — enchant a basic card with Spiral, or drink to heal.

    Source: SpiralingWhirlpool.cs
      IsAllowed: the deck has a card Spiral can enchant (a Basic Strike/Defend)
      CalculateVars: Heal = 33% of Max HP
      OBSERVE: enchant 1 chosen eligible card with Spiral (played 1 extra time)
      DRINK:   heal 33% of Max HP
    """

    id = "spiraling_whirlpool"
    name = "Spiraling Whirlpool"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.heal = 0

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return any(SpiralEnchantment.can_enchant(c) for c in run.deck)

    def calculate_vars(self) -> None:
        self.heal = self.run.max_hp * 33 // 100  # (decimal)MaxHp * 0.33m, truncated

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("OBSERVE", self._observe),
            EventOption("DRINK", self._drink),
        ]

    def _observe(self) -> None:
        candidates = [c for c in self.run.deck if SpiralEnchantment.can_enchant(c)]
        for card in self.run.select_cards("enchant", candidates, 1):
            make_enchantment("spiral").attach(card)
        self._finish("OBSERVE")

    def _drink(self) -> None:
        self.run.heal(self.heal)
        self._finish("DRINK")
