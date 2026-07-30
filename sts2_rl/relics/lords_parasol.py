from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LordsParasol(Relic):
    """LordsParasol.cs — on entering a merchant room, buy EVERYTHING in the
    inventory for free (OnTryPurchaseWrapper with ignoreCost for every card,
    relic and potion entry) AND take the free card removal.

    The port used to skip the removal, justified with "the card-removal service
    is not an item and is not bought". That claim is false against the source:
    LordsParasol.cs:102-107 is `if (inventory.CardRemovalEntry != null) { ...
    await inventory.CardRemovalEntry.OnTryPurchaseWrapper(inventory,
    ignoreCost: true, cancelable: false); ... }` — outside the try/finally, after
    the three item loops, and with `cancelable: false`, so the player MUST remove
    a card. Skipping it left the deck permanently one card larger in every
    merchant room the relic saw, and deck contents are what the conformance
    runner compares.
    """

    id = "lords_parasol"
    name = "Lord's Parasol"
    rarity = RelicRarity.ANCIENT

    def after_shop_entered(self, run, shop) -> None:
        from ..shop import MerchantCardRemovalEntry

        removal = None
        for entry in shop.all_entries:
            if isinstance(entry, MerchantCardRemovalEntry):
                # Held back, not skipped: C# buys it LAST, after the card, relic
                # and potion loops and outside their try/finally.
                removal = entry
                continue
            if entry.is_stocked:
                entry.purchase(ignore_cost=True)
        # LordsParasol.cs:102-107 — the free, non-cancelable removal.
        if removal is not None and removal.is_stocked:
            removal.purchase(ignore_cost=True)
