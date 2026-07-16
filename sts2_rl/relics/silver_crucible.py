from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SilverCrucible(Relic):
    """SilverCrucible.cs — your next 3 card rewards offer upgraded cards, but
    the first treasure room you enter holds no chest."""

    id = "silver_crucible"
    name = "Silver Crucible"
    rarity = RelicRarity.ANCIENT
    CARD_REWARDS = 3

    def __init__(self) -> None:
        super().__init__()
        self.times_used = 0
        self.treasure_rooms_entered = 0

    def modify_card_reward_options(self, run, cards) -> None:
        if self.times_used >= self.CARD_REWARDS:
            return
        for card in cards:
            if card.is_upgradable:
                card.upgrade()
        self.times_used += 1

    def after_room_entered(self, run, point, room_type) -> None:
        from ..rooms import RoomType

        if room_type == RoomType.TREASURE:
            self.treasure_rooms_entered += 1

    def should_generate_treasure(self, run) -> bool:
        return self.treasure_rooms_entered > 1
