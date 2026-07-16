from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PhialHolster(Relic):
    """PhialHolster.cs — gain 1 potion slot and 2 random potions."""

    id = "phial_holster"
    name = "Phial Holster"
    rarity = RelicRarity.ANCIENT
    POTION_SLOTS = 1
    POTIONS = 2

    def after_obtained(self, run) -> None:
        run.max_potions += self.POTION_SLOTS
        for potion in run.random_potions(self.POTIONS, distinct=True):
            run.add_potion(potion)
