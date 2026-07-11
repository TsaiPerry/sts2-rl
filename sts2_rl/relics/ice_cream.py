from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class IceCream(Relic):
    """Energy is conserved between turns (turn-start energy is added to your
    current energy instead of replacing it)."""

    id = "ice_cream"
    name = "Ice Cream"
    rarity = RelicRarity.RARE

    def should_reset_energy(self, player: PlayerCombatState) -> bool:
        return self.turn == 1
