from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Mango(Relic):
    """Upon pickup, raise Max HP by 14 — an out-of-combat pickup effect, so
    this is a no-op stub."""

    id = "mango"
    name = "Mango"
    rarity = RelicRarity.RARE
