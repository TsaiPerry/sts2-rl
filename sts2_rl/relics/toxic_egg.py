from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ToxicEgg(Relic):
    """Skill cards added to your deck are Upgraded — an out-of-combat deck edit,
    so this is a no-op stub."""

    id = "toxic_egg"
    name = "Toxic Egg"
    rarity = RelicRarity.RARE
