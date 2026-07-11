from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class OldCoin(Relic):
    """Upon pickup, gain 300 gold — no gold system in the sim, so this is a
    no-op stub."""

    id = "old_coin"
    name = "Old Coin"
    rarity = RelicRarity.RARE
