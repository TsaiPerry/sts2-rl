from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Orichalcum(Relic):
    """At the end of your turn, if you have no Block, gain 6 Block."""

    id = "orichalcum"
    name = "Orichalcum"
    rarity = RelicRarity.UNCOMMON

    BLOCK = 6

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if player.block == 0:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED)
