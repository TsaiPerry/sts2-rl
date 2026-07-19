from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LoomingFruit(Relic):
    """Upon pickup, raise Max HP by 31 — an out-of-combat pickup effect, so
    this is a no-op stub."""

    id = "looming_fruit"
    name = "Looming Fruit"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
