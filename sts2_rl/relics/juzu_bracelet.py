from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic

@register_relic
class JuzuBracelet(Relic):
    """JuzuBracelet.cs — a "?" node can never roll a combat."""

    id = "juzu_bracelet"
    name = "Juzu Bracelet"
    rarity = RelicRarity.COMMON

    def modify_unknown_map_point_room_types(self, run, room_types):
        """JuzuBracelet.cs:17-27 — copy the incoming set and drop Monster.
        Only Monster: an Elite "?" is still possible."""
        from ..rooms import RoomType

        return set(room_types) - {RoomType.MONSTER}

    @classmethod
    def is_allowed(cls, run) -> bool:
        """JuzuBracelet.cs:12-15: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
