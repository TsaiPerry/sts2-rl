from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Strawberry(Relic):
    """Upon pickup, raise Max HP by 7 — an out-of-combat pickup effect, so this
    is a no-op stub."""

    id = "strawberry"
    name = "Strawberry"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
