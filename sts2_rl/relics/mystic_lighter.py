from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MysticLighter(Relic):
    """Your Enchanted Attacks deal 9 additional damage — the sim has no
    enchantments, so this is a no-op stub."""

    id = "mystic_lighter"
    name = "Mystic Lighter"
    rarity = RelicRarity.SHOP
