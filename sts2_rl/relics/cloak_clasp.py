from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class CloakClasp(Relic):
    """At the end of your turn, gain 1 Block for each card in your hand."""

    id = "cloak_clasp"
    name = "Cloak Clasp"
    rarity = RelicRarity.RARE

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if player.hand:
            from ..cmds import BlockCmd
            BlockCmd.apply(
                self.hooks, player, len(player.hand), props=ValueProp.UNPOWERED
            )
