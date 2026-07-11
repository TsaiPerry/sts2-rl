from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Shovel(Relic):
    """Adds a Dig option at rest sites — an out-of-combat rest-site modifier,
    so this is a no-op stub."""

    id = "shovel"
    name = "Shovel"
    rarity = RelicRarity.RARE
