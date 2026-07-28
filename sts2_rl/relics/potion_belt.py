from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PotionBelt(Relic):
    """PotionBelt.cs — upon pickup, gain 2 potion slots (AfterObtained ->
    PlayerCmd.GainMaxPotionCount(IntVar "PotionSlots" = 2))."""

    id = "potion_belt"
    name = "Potion Belt"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    POTION_SLOTS = 2

    def after_obtained(self, run) -> None:
        run.add_potion_slots(self.POTION_SLOTS)
