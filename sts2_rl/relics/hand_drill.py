from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class HandDrill(Relic):
    """Whenever you break an enemy's block, apply 2 Vulnerable to it.

    Source: HandDrill.cs — AfterDamageGiven when result.WasBlockBroken. The
    sim's damage pipeline does not surface a block-broken flag to relics, so
    this is a documented stub. Granted by the Trash Heap event."""

    id = "hand_drill"
    name = "Hand Drill"
    rarity = RelicRarity.EVENT
