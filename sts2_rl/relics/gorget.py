from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Gorget(Relic):
    """Start each combat with 4 Plating (gain 4 Block at the end of your
    turn; Plating decays 1 per turn)."""

    id = "gorget"
    name = "Gorget"
    rarity = RelicRarity.COMMON

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import PlatingPower
        PowerCmd.apply(self.hooks, self.player, PlatingPower, 4, applier=self.player)
