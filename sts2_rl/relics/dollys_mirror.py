from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class DollysMirror(Relic):
    """Upon pickup, duplicate a card in your deck — out-of-combat pickup
    effect, stub."""

    id = "dollys_mirror"
    name = "Dolly's Mirror"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
