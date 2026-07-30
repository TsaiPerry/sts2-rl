from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Akabeko(Relic):
    """At the start of combat, gain 8 Vigor (your next attack deals +8)."""

    id = "akabeko"
    name = "Akabeko"
    rarity = RelicRarity.UNCOMMON

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import PowerCmd
            from ..powers import VigorPower
            PowerCmd.apply(self.hooks, player, VigorPower, 8, applier=player)
