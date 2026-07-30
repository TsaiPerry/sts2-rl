from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Lantern(Relic):
    """Gain 1 energy on the first turn of each combat."""

    id = "lantern"
    name = "Lantern"
    rarity = RelicRarity.COMMON

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, 1)
