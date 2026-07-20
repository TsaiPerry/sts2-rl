from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Sozu(Relic):
    """Sozu.cs — gain 1 extra energy each turn, but you can no longer obtain
    potions (ShouldProcurePotion is false for the owner). Offered by the Darv
    shrine in act 2."""

    id = "sozu"
    name = "Sozu"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def should_procure_potion(self, run, potion) -> bool:
        return False
