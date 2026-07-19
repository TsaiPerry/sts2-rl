from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NutritiousOyster(Relic):
    """NutritiousOyster.cs — gain 11 Max HP."""

    id = "nutritious_oyster"
    name = "Nutritious Oyster"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    MAX_HP = 11

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)
