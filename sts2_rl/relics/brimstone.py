from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Brimstone(Relic):
    """At the start of your turn, gain 2 Strength and ALL enemies gain
    1 Strength."""

    id = "brimstone"
    name = "Brimstone"
    rarity = RelicRarity.SHOP

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        from ..cmds import PowerCmd
        from ..powers import StrengthPower
        PowerCmd.apply(self.hooks, player, StrengthPower, 2, applier=player)
        for enemy in self.living_enemies():
            PowerCmd.apply(self.hooks, enemy, StrengthPower, 1)
