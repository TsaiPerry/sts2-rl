from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PaelsBlood(Relic):
    """PaelsBlood.cs — draw 1 extra card each turn (ModifyHandDraw,
    CardsVar(1))."""

    id = "paels_blood"
    name = "Pael's Blood"
    rarity = RelicRarity.ANCIENT

    CARDS = 1

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        return count + self.CARDS
