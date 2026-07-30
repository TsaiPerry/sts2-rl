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

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.is_used_up or self.turn > 1:
            return
        # BoneTea.cs:53-56 upgrades the hand through CardCmd.Upgrade, which
        # skips a card whose IsUpgradable is false -- and Statuses reach the
        # opening hand routinely (Blessed Antler shuffles three Dazed into the
        # turn-1 draw pile, and Bone Tea fires post-draw).
        from ..cmds import CardCmd
        for card in player.hand:
            CardCmd.upgrade(self.hooks, card)
        self.combats_left -= 1
