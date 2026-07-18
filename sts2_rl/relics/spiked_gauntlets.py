from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class SpikedGauntlets(Relic):
    """SpikedGauntlets.cs — +1 max Energy (EnergyVar(1)); your Power cards
    cost 1 more (TryModifyEnergyCostInCombat)."""

    id = "spiked_gauntlets"
    name = "Spiked Gauntlets"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def modify_card_energy_cost(self, card: "Card", cost: int) -> int:
        from ..cards import CardType

        if card.card_type == CardType.POWER:
            return cost + 1
        return cost
