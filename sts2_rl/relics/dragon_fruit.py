from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class DragonFruit(Relic):
    """Whenever you gain gold, gain 1 Max HP — no gold system, stub."""

    id = "dragon_fruit"
    name = "Dragon Fruit"
    rarity = RelicRarity.SHOP
