from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..creatures import Creature

@register_relic
class Anchor(Relic):
    """Start each combat with 10 Block (BeforeCombatStart in the game; the
    sim grants it after the turn-1 block clear so it survives into the first
    enemy turn)."""

    id = "anchor"
    name = "Anchor"
    rarity = RelicRarity.COMMON

    def on_block_cleared(self, target: Creature) -> None:
        if target is self.player and self.turn == 1:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, 10, props=ValueProp.UNPOWERED)
