from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class WhiteBeastStatue(Relic):
    """WhiteBeastStatue.cs — every combat room's rewards include a potion
    (ShouldForcePotionReward for any RoomType.IsCombatRoom())."""

    id = "white_beast_statue"
    name = "White Beast Statue"
    rarity = RelicRarity.RARE

    def should_force_potion_reward(self, run, room_type) -> bool:
        from ..rooms import RoomType

        return room_type in (RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """WhiteBeastStatue.cs:12-15: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
