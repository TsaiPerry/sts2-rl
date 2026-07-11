from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Vajra(Relic):
    """At the start of combat, gain 1 Strength."""

    id = "vajra"
    name = "Vajra"
    rarity = RelicRarity.COMMON

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import StrengthPower
        PowerCmd.apply(self.hooks, self.player, StrengthPower, 1, applier=self.player)
