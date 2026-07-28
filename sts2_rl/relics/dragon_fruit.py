from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class DragonFruit(Relic):
    """Whenever you gain gold, gain 1 Max HP — no gold system, stub."""

    id = "dragon_fruit"
    name = "Dragon Fruit"
    rarity = RelicRarity.SHOP

    @classmethod
    def is_allowed(cls, run) -> bool:
        """DragonFruit.cs:17-20: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
