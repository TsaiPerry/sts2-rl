from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TheCourier(Relic):
    """TheCourier.cs — shop prices are 20% off (ModifyMerchantPrice) and a
    bought slot restocks instead of clearing (ShouldRefillMerchantEntry)."""

    id = "the_courier"
    name = "The Courier"
    rarity = RelicRarity.RARE
    is_allowed_in_shops = False  # TheCourier.IsAllowedInShops

    DISCOUNT = 20  # DynamicVar("Discount", 20m)

    def modify_merchant_price(self, run, entry, original_price):
        """Hook.ModifyMerchantPrice (TheCourier.cs:20-26):
        `originalPrice * (1m - Discount / 100m)` — 80% of the price, which
        MerchantEntry.Cost then truncates with `(int)`."""
        return original_price * (100 - self.DISCOUNT) / 100

    def should_refill_merchant_entry(self, run, entry) -> bool:
        """Hook.ShouldRefillMerchantEntry (TheCourier.cs:28-31): true for the
        owner, so MerchantEntry.OnTryPurchaseWrapper calls RestockAfterPurchase
        instead of ClearAfterPurchase."""
        return True
