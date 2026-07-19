from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WarPaint(Relic):
    """Upon pickup, Upgrade 2 random Skills in your deck — an out-of-combat deck
    edit, so this is a no-op stub."""

    id = "war_paint"
    name = "War Paint"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
