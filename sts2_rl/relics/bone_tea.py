from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BoneTea(Relic):
    """BoneTea.cs — in your NEXT combat only, upgrade every card in your
    opening hand. Fires from AfterSideTurnStart on turn 1 (post-draw), then
    spends its single charge. Bought at the Tea Master event for 50 gold."""

    id = "bone_tea"
    name = "Bone Tea"
    rarity = RelicRarity.EVENT

    COMBATS = 1

    def __init__(self) -> None:
        super().__init__()
        self.combats_left = self.COMBATS

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => CombatsLeft <= 0
        return self.combats_left <= 0

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.is_used_up or self.turn > 1:
            return
        for card in player.hand:
            card.upgrade()
        self.combats_left -= 1
