from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class JuzuBracelet(Relic):
    """Unknown map rooms are no longer combats — map-only effect, stub."""

    id = "juzu_bracelet"
    name = "Juzu Bracelet"
    rarity = RelicRarity.COMMON

    @classmethod
    def is_allowed(cls, run) -> bool:
        """JuzuBracelet.cs:12-15: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
