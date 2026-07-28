from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class GamePiece(Relic):
    """Whenever you play a Power card, draw 1 card."""

    id = "game_piece"
    name = "Game Piece"
    rarity = RelicRarity.RARE

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type == CardType.POWER:
            from ..cmds import DrawCmd
            DrawCmd.draw(self.player, 1)
