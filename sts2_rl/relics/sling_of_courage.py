from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SlingOfCourage(Relic):
    """At the start of Elite combats, gain 2 Strength — the sim has no room-type
    context (it can't tell an elite fight from any other), so this is a no-op
    stub."""

    id = "sling_of_courage"
    name = "Sling of Courage"
    rarity = RelicRarity.SHOP
