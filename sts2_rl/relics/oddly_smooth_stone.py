from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class OddlySmoothStone(Relic):
    """At the start of combat, gain 1 Dexterity."""

    id = "oddly_smooth_stone"
    name = "Oddly Smooth Stone"
    rarity = RelicRarity.COMMON

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import DexterityPower
        PowerCmd.apply(self.hooks, self.player, DexterityPower, 1, applier=self.player)
