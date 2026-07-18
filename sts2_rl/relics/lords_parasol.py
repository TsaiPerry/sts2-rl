from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LordsParasol(Relic):
    """LordsParasol.cs — on entering a merchant room, buy EVERYTHING in the
    inventory for free (OnTryPurchaseWrapper with ignoreCost for every card,
    relic, and potion entry; the card-removal service is not an item and is
    not bought)."""

    id = "lords_parasol"
    name = "Lord's Parasol"
    rarity = RelicRarity.ANCIENT

    def after_shop_entered(self, run, shop) -> None:
        from ..shop import MerchantCardRemovalEntry

        for entry in shop.all_entries:
            if isinstance(entry, MerchantCardRemovalEntry):
                continue
            if entry.is_stocked:
                entry.purchase(ignore_cost=True)
