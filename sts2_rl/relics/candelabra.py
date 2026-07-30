from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Candelabra(Relic):
    """At the start of turn 2, gain 2 energy."""

    id = "candelabra"
    name = "Candelabra"
    rarity = RelicRarity.UNCOMMON

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn == 2:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, 2)
