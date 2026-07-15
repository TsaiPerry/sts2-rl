from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TheCourier(Relic):
    """Shop prices are 20% off and the shop restocks — an out-of-combat merchant
    effect, so this is a no-op stub."""

    id = "the_courier"
    name = "The Courier"
    rarity = RelicRarity.RARE
    is_allowed_in_shops = False  # TheCourier.IsAllowedInShops
