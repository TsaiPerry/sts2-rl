from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LuckyFysh(Relic):
    """Whenever a card is added to your deck, gain 15 gold — no gold system
    in the sim, so this is a no-op stub."""

    id = "lucky_fysh"
    name = "Lucky Fysh"
    rarity = RelicRarity.UNCOMMON
    is_allowed_in_shops = False  # LuckyFysh.IsAllowedInShops
