from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MiniatureTent(Relic):
    """At rest sites, you may take a second action — an out-of-combat rest-site
    modifier, so this is a no-op stub."""

    id = "miniature_tent"
    name = "Miniature Tent"
    rarity = RelicRarity.SHOP
