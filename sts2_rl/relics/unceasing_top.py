from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class UnceasingTop(Relic):
    """Whenever your hand is empty during your turn, draw 1 card. Detected as
    the hand emptying from a card play (mirrors AfterHandEmptied during the
    play phase — not the end-of-turn flush)."""

    id = "unceasing_top"
    name = "Unceasing Top"
    rarity = RelicRarity.RARE

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if (
            not self.combat.is_over
            and self.combat.current_side == "player"
            and not self.player.hand
        ):
            from ..cmds import DrawCmd
            DrawCmd.draw(self.player, 1)
