from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class Planisphere(Relic):
    """Planisphere.cs — heal 5 HP on entering a `?` node (AfterRoomEntered
    gates on `RunState.CurrentMapPoint.PointType == MapPointType.Unknown`,
    which is the MAP POINT's type, not the room the `?` resolved into)."""

    id = "planisphere"
    name = "Planisphere"
    rarity = RelicRarity.UNCOMMON

    HEAL = 5   # HealVar(5)

    def after_room_entered(self, run, point, room_type) -> None:
        from ..actmap import MapPointType

        if run.is_dead or point is None:
            return
        if point.point_type == MapPointType.UNKNOWN:
            run.heal(self.HEAL)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """Planisphere.cs:18-21: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
