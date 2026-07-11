from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Planisphere(Relic):
    """Heal 5 HP whenever you enter an unknown room — an out-of-combat map
    effect, so this is a no-op stub."""

    id = "planisphere"
    name = "Planisphere"
    rarity = RelicRarity.UNCOMMON
