from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PunchDagger(Relic):
    """Upon pickup, enchant a card with Momentum — the sim has no enchantments,
    so this is a no-op stub."""

    id = "punch_dagger"
    name = "Punch Dagger"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
