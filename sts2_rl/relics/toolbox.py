from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Toolbox(Relic):
    """At the start of your first turn, choose 1 of 3 Colorless cards to add to
    your hand — the sim models no Colorless card pool or generation for it, so
    this is a no-op stub."""

    id = "toolbox"
    name = "Toolbox"
    rarity = RelicRarity.SHOP
