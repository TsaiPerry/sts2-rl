from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MembershipCard(Relic):
    """MembershipCard.cs — shop prices are 50% off (ModifyMerchantPrice)."""

    id = "membership_card"
    name = "Membership Card"
    rarity = RelicRarity.SHOP

    DISCOUNT = 50  # DynamicVar("Discount", 50m)

    def modify_merchant_price(self, run, entry, original_price):
        """Hook.ModifyMerchantPrice (MembershipCard.cs:18-29):
        `originalPrice * (Discount / 100m)`. The decimal arithmetic matters —
        MerchantEntry.Cost truncates the result with `(int)`, so 175 → 87."""
        return original_price * self.DISCOUNT / 100
