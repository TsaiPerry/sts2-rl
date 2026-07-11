from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PetrifiedToad(Relic):
    """At the start of each combat, procure a Potion Shaped Rock — the sim
    doesn't model that potion or potion procurement, so this is a no-op stub."""

    id = "petrified_toad"
    name = "Petrified Toad"
    rarity = RelicRarity.UNCOMMON
