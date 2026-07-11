from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class TheAbacus(Relic):
    """Whenever you shuffle your draw pile, gain 6 Block."""

    id = "the_abacus"
    name = "The Abacus"
    rarity = RelicRarity.SHOP

    BLOCK = 6

    def on_shuffle(self, player: PlayerCombatState) -> None:
        if player is self.player:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, self.BLOCK, props=ValueProp.UNPOWERED)
