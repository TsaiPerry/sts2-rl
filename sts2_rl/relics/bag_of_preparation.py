from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class BagOfPreparation(Relic):
    """At the start of combat, draw 2 additional cards."""

    id = "bag_of_preparation"
    name = "Bag of Preparation"
    rarity = RelicRarity.COMMON

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        if self.turn == 1:
            return count + 2
        return count
