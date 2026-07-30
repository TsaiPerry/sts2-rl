from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class DragonFruit(Relic):
    """DragonFruit.cs — whenever you gain gold, gain 1 Max HP."""

    id = "dragon_fruit"
    name = "Dragon Fruit"
    rarity = RelicRarity.SHOP

    MAX_HP = 1   # CanonicalVars: MaxHpVar(1)

    def after_gold_gained(self, run, amount: int) -> None:
        """DragonFruit.cs:22-29 — `AfterGoldGained(player)`, owner only, then
        `CreatureCmd.GainMaxHp(MaxHp)`. The amount is not consulted: any
        positive gain pays exactly 1."""
        run.gain_max_hp(self.MAX_HP)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """DragonFruit.cs:17-20: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
