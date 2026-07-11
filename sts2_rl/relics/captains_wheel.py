from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..creatures import Creature

@register_relic
class CaptainsWheel(Relic):
    """At the start of turn 3, gain 18 Block."""

    id = "captains_wheel"
    name = "Captain's Wheel"
    rarity = RelicRarity.RARE

    def on_block_cleared(self, target: Creature) -> None:
        if target is self.player and self.turn == 3:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, 18, props=ValueProp.UNPOWERED)
