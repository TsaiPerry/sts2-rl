from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SeaGlass(Relic):
    """SeaGlass.cs — upon pickup, a grid pick from another character's card
    pool (15 cards: 5 Common / 5 Uncommon / 5 Rare of the assigned character).
    Cross-character card generation is out of scope for the single-character
    sim, so this is a documented no-op stub (the Orobas option can still be
    chosen; it simply grants nothing)."""

    id = "sea_glass"
    name = "Sea Glass"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
