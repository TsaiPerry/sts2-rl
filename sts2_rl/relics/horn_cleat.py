from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..creatures import Creature

@register_relic
class HornCleat(Relic):
    """At the start of turn 2, gain 14 Block."""

    id = "horn_cleat"
    name = "Horn Cleat"
    rarity = RelicRarity.UNCOMMON

    def on_block_cleared(self, target: Creature) -> None:
        if target is self.player and self.turn == 2:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, 14, props=ValueProp.UNPOWERED)
