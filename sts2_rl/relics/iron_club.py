from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class IronClub(Relic):
    """IronClub.cs — every 6th card you play, draw 1 card (CardsVar(6); the
    counter is a SavedProperty, so it persists across combats)."""

    id = "iron_club"
    name = "Iron Club"
    rarity = RelicRarity.ANCIENT

    CARDS = 6

    def __init__(self) -> None:
        super().__init__()
        self.cards_played = 0

    def on_card_played(self, card: "Card") -> None:
        from ..cmds import DrawCmd

        self.cards_played += 1
        if self.cards_played % self.CARDS == 0:
            DrawCmd.draw(self.player, 1)
