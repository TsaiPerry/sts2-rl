from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WingCharm(Relic):
    """One card in each card reward is enchanted with Swift — the sim has no
    enchantments or card rewards, so this is a no-op stub."""

    id = "wing_charm"
    name = "Wing Charm"
    rarity = RelicRarity.SHOP
