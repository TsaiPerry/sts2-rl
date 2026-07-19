from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Orrery(Relic):
    """Upon pickup, choose 5 cards to add to your deck — an out-of-combat card
    reward, so this is a no-op stub."""

    id = "orrery"
    name = "Orrery"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
