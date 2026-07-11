from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class JuzuBracelet(Relic):
    """Unknown map rooms are no longer combats — map-only effect, stub."""

    id = "juzu_bracelet"
    name = "Juzu Bracelet"
    rarity = RelicRarity.COMMON
