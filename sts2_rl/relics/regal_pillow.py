from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RegalPillow(Relic):
    """Heal an additional 15 HP when you Rest — an out-of-combat rest-site
    effect, so this is a no-op stub."""

    id = "regal_pillow"
    name = "Regal Pillow"
    rarity = RelicRarity.COMMON
