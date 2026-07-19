from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class GoldenPearl(Relic):
    """GoldenPearl.cs — gain 150 gold."""

    id = "golden_pearl"
    name = "Golden Pearl"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    GOLD = 150

    def after_obtained(self, run) -> None:
        run.gain_gold(self.GOLD)
