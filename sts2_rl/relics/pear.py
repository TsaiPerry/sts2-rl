from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Pear(Relic):
    """Upon pickup, raise Max HP by 10 — an out-of-combat pickup effect, so
    this is a no-op stub."""

    id = "pear"
    name = "Pear"
    rarity = RelicRarity.UNCOMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
