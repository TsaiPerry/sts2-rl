from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WhiteBeastStatue(Relic):
    """Combats always drop a potion — an out-of-combat reward modifier, so this
    is a no-op stub."""

    id = "white_beast_statue"
    name = "White Beast Statue"
    rarity = RelicRarity.RARE
