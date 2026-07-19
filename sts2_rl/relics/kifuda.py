from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Kifuda(Relic):
    """Upon pickup, enchant up to 3 cards with Adroit — no enchantments in
    the sim, stub."""

    id = "kifuda"
    name = "Kifuda"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
