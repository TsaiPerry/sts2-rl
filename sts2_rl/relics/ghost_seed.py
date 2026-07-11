from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class GhostSeed(Relic):
    """Your basic Strikes and Defends are Ethereal."""

    id = "ghost_seed"
    name = "Ghost Seed"
    rarity = RelicRarity.SHOP

    @staticmethod
    def _can_affect(card: Card) -> bool:
        from ..cards import CardRarity
        return (
            card.rarity == CardRarity.BASIC
            and ("strike" in card.tags or "defend" in card.tags)
            and not card.is_ethereal
        )

    def on_combat_start(self) -> None:
        for card in self.player.all_cards:
            if self._can_affect(card):
                card.is_ethereal = True

    def on_card_entered_combat(self, card: Card) -> None:
        if self._can_affect(card):
            card.is_ethereal = True
