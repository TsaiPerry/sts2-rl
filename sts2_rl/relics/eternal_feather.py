from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class EternalFeather(Relic):
    """Heal 3 HP per 5 deck cards at rest sites — out-of-combat, stub."""

    id = "eternal_feather"
    name = "Eternal Feather"
    rarity = RelicRarity.UNCOMMON
