from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PaelsFlesh(Relic):
    """PaelsFlesh.cs — from turn 3 onward, +1 max Energy (ModifyMaxEnergy
    gated on TurnNumber >= 3; EnergyVar(1))."""

    id = "paels_flesh"
    name = "Pael's Flesh"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    FROM_TURN = 3

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        if self.turn < self.FROM_TURN:
            return amount
        return amount + self.ENERGY
