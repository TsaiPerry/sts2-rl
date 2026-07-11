from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WhiteStar(Relic):
    """Elite fights drop an additional (Boss-tier) card reward — an out-of-combat
    reward modifier, so this is a no-op stub."""

    id = "white_star"
    name = "White Star"
    rarity = RelicRarity.RARE
