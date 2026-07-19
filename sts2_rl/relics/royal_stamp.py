from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RoyalStamp(Relic):
    """Upon pickup, enchant a card with Royally Approved — the sim has no
    enchantments, so this is a no-op stub."""

    id = "royal_stamp"
    name = "Royal Stamp"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
