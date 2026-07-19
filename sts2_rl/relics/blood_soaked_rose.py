from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BloodSoakedRose(Relic):
    """BloodSoakedRose.cs — +1 max Energy (EnergyVar(1)); upon pickup, add an
    Enthralled curse to the deck (AddCurseToDeck<Enthralled>)."""

    id = "blood_soaked_rose"
    name = "Blood-Soaked Rose"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    ENERGY = 1

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("enthralled"))

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY
