from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class AlchemicalCoffer(Relic):
    """AlchemicalCoffer.cs — upon pickup, gain 4 potion slots (PotionSlots
    DynamicVar) and fill them with 4 random potions."""

    id = "alchemical_coffer"
    name = "Alchemical Coffer"
    rarity = RelicRarity.ANCIENT

    POTION_SLOTS = 4

    def after_obtained(self, run) -> None:
        run.max_potions += self.POTION_SLOTS
        for potion in run.random_potions(self.POTION_SLOTS):
            run.add_potion(potion)
