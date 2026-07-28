from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class OldCoin(Relic):
    """OldCoin.cs — upon pickup, gain 300 gold (AfterObtained ->
    PlayerCmd.GainGold(GoldVar(300)))."""

    id = "old_coin"
    name = "Old Coin"
    rarity = RelicRarity.RARE
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    is_allowed_in_shops = False  # OldCoin.IsAllowedInShops

    GOLD = 300

    def after_obtained(self, run) -> None:
        run.gain_gold(self.GOLD)

    def undo_after_obtained(self, run) -> None:
        # Conformance-only reversal (see Relic.undo_after_obtained): the
        # pickup moved run state outside run.relics, so a relic the save did
        # not really pick has to give the gold back. Re-run the same
        # Hook.ModifyGoldGained chain gain_gold used so a Bowler Hat / Ectoplasm
        # in the list is unwound by the amount it actually credited.
        amount: float = self.GOLD
        for relic in list(run.relics):
            amount = relic.modify_gold_gained(run, amount)
        run.lose_gold(int(amount) if amount > 0 else 0)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """OldCoin.cs:20-23: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
