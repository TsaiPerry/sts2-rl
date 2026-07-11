from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LastingCandy(Relic):
    """Every other combat, a card reward is replaced with a Power card — a
    card-reward modifier that runs between combats, so this is a no-op stub."""

    id = "lasting_candy"
    name = "Lasting Candy"
    rarity = RelicRarity.UNCOMMON
