from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class BronzeScales(Relic):
    """Start each combat with 3 Thorns."""

    id = "bronze_scales"
    name = "Bronze Scales"
    rarity = RelicRarity.COMMON

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import ThornsPower
        PowerCmd.apply(self.hooks, self.player, ThornsPower, 3, applier=self.player)
