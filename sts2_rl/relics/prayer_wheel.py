from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PrayerWheel(Relic):
    """Normal enemies drop an additional card reward — an out-of-combat reward
    modifier, so this is a no-op stub."""

    id = "prayer_wheel"
    name = "Prayer Wheel"
    rarity = RelicRarity.RARE
