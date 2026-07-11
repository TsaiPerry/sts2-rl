from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LeesWaffle(Relic):
    """Upon pickup, raise Max HP by 7 and heal to full — an out-of-combat
    pickup effect, so this is a no-op stub."""

    id = "lees_waffle"
    name = "Lee's Waffle"
    rarity = RelicRarity.SHOP
