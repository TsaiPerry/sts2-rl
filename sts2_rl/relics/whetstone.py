from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Whetstone(Relic):
    """Upon pickup, Upgrade 2 random Attacks in your deck — an out-of-combat
    deck edit, so this is a no-op stub."""

    id = "whetstone"
    name = "Whetstone"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
