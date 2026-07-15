from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class BowlerHat(Relic):
    """Gain 25% more gold — out-of-combat only (no gold system), stub."""

    id = "bowler_hat"
    name = "Bowler Hat"
    rarity = RelicRarity.UNCOMMON
    is_allowed_in_shops = False  # BowlerHat.IsAllowedInShops
