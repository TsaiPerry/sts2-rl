from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class GnarledHammer(Relic):
    """Upon pickup, enchant up to 3 cards with Sharp — no enchantments in
    the sim, stub."""

    id = "gnarled_hammer"
    name = "Gnarled Hammer"
    rarity = RelicRarity.SHOP
