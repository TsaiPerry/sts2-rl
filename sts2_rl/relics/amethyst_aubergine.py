from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class AmethystAubergine(Relic):
    """Combat rewards grant 15 extra gold — out-of-combat only (the sim has
    no gold), so this is a no-op stub."""

    id = "amethyst_aubergine"
    name = "Amethyst Aubergine"
    rarity = RelicRarity.COMMON
    is_allowed_in_shops = False  # AmethystAubergine.IsAllowedInShops
