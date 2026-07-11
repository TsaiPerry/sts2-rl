from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class UnsettlingLamp(Relic):
    """The first Debuff you apply to an enemy with a card each combat is doubled.
    Faithful support needs card-source tracking through power application plus a
    power-amount multiplier hook, neither of which the sim models, so this is a
    no-op stub."""

    id = "unsettling_lamp"
    name = "Unsettling Lamp"
    rarity = RelicRarity.RARE
