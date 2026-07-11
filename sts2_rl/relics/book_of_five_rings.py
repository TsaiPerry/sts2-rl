from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class BookOfFiveRings(Relic):
    """Every 5 cards added to your deck, heal 20 HP — deck edits happen
    between combats, so this is a no-op stub."""

    id = "book_of_five_rings"
    name = "Book of Five Rings"
    rarity = RelicRarity.COMMON
