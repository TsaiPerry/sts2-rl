from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class SparklingRouge(Relic):
    """At the start of turn 3, gain 1 Strength and 1 Dexterity."""

    id = "sparkling_rouge"
    name = "Sparkling Rouge"
    rarity = RelicRarity.UNCOMMON

    def on_block_cleared(self, player: PlayerCombatState) -> None:
        if self.turn == 3:
            from ..cmds import PowerCmd
            from ..powers import DexterityPower, StrengthPower
            PowerCmd.apply(self.hooks, player, StrengthPower, 1, applier=player)
            PowerCmd.apply(self.hooks, player, DexterityPower, 1, applier=player)
