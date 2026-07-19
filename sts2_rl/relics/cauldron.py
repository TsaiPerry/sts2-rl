from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Cauldron(Relic):
    """Upon pickup, brew 5 potions — out-of-combat pickup effect, stub."""

    id = "cauldron"
    name = "Cauldron"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
