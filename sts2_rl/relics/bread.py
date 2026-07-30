from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class Bread(Relic):
    """Gain 1 extra energy each turn. On turn 1, lose 2 energy."""

    id = "bread"
    name = "Bread"
    rarity = RelicRarity.SHOP

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        if self.turn == 1:
            return amount
        return amount + 1

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn == 1:
            player.energy = max(0, player.energy - 2)
