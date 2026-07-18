from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SignetRing(Relic):
    """SignetRing.cs — upon pickup, gain 999 gold (GoldVar(999))."""

    id = "signet_ring"
    name = "Signet Ring"
    rarity = RelicRarity.ANCIENT

    GOLD = 999

    def after_obtained(self, run) -> None:
        run.gain_gold(self.GOLD)
