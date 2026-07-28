from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class MealTicket(Relic):
    """MealTicket.cs — entering a MerchantRoom heals 15 HP
    (AfterRoomEntered, skipped when the owner is dead)."""

    id = "meal_ticket"
    name = "Meal Ticket"
    rarity = RelicRarity.COMMON

    HEAL = 15   # HealVar(15)

    def after_room_entered(self, run, point, room_type) -> None:
        from ..rooms import RoomType

        if room_type == RoomType.SHOP and not run.is_dead:
            run.heal(self.HEAL)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """MealTicket.cs:17-20: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
