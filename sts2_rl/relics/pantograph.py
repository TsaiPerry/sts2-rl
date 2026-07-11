from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Pantograph(Relic):
    """At the start of Boss combats, heal 25 HP — the sim has no room-type
    context (it can't tell a boss fight from any other), so this is a no-op
    stub."""

    id = "pantograph"
    name = "Pantograph"
    rarity = RelicRarity.UNCOMMON
