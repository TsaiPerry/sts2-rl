from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class VeryHotCocoa(Relic):
    """At the start of combat, gain 4 energy."""

    id = "very_hot_cocoa"
    name = "Very Hot Cocoa"
    rarity = RelicRarity.ANCIENT

    ENERGY = 4

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, self.ENERGY)
