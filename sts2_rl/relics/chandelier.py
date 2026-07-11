from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Chandelier(Relic):
    """At the start of turn 3, gain 3 energy."""

    id = "chandelier"
    name = "Chandelier"
    rarity = RelicRarity.RARE

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn == 3:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, 3)
