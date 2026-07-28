from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class BowlerHat(Relic):
    """BowlerHat.cs — gain 25% more gold (ModifyGoldGained multiplies the
    amount by DynamicVar "GoldIncrease" = 1.25). `RunState.gain_gold` runs the
    chain and truncates the product, like PlayerCmd.GainGold."""

    id = "bowler_hat"
    name = "Bowler Hat"
    rarity = RelicRarity.UNCOMMON
    is_allowed_in_shops = False  # BowlerHat.IsAllowedInShops

    GOLD_INCREASE = 1.25

    def modify_gold_gained(self, run, amount: float) -> float:
        return amount * self.GOLD_INCREASE

    @classmethod
    def is_allowed(cls, run) -> bool:
        """BowlerHat.cs:20-23: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
