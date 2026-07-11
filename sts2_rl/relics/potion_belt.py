from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PotionBelt(Relic):
    """Upon pickup, gain 2 potion slots — an out-of-combat capacity change, so
    this is a no-op stub."""

    id = "potion_belt"
    name = "Potion Belt"
    rarity = RelicRarity.COMMON
