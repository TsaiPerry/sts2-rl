from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class FrozenEgg(Relic):
    """Power cards added to your deck are Upgraded — out-of-combat, stub."""

    id = "frozen_egg"
    name = "Frozen Egg"
    rarity = RelicRarity.RARE
