from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RunicPyramid(Relic):
    """RunicPyramid.cs — you no longer discard your hand at the end of your
    turn (ShouldFlush returns false for the owner). Offered by the Darv
    shrine."""

    id = "runic_pyramid"
    name = "Runic Pyramid"
    rarity = RelicRarity.ANCIENT

    def should_flush_hand(self) -> bool:
        return False
