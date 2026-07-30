from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PrayerWheel(Relic):
    """PrayerWheel.cs — a Monster room's rewards carry a SECOND card choice on
    the same Monster odds (`TryModifyRewards` adds
    `new CardReward(CardCreationOptions.ForRoom(player, RoomType.Monster), 3)`).

    It is a separate CardReward on the set, so it is a separate pick-one-of-3
    and the player can keep a card from each. Its options are drawn when
    RewardsSet.GenerateWithoutOffering populates the rewards the hooks added,
    i.e. AFTER both ModifyRewards passes (RewardsSet.cs:137-143) — appending an
    unpopulated group here is what puts those three Rewards-stream draws in the
    right place.
    """

    id = "prayer_wheel"
    name = "Prayer Wheel"
    rarity = RelicRarity.RARE

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rewards import CardRewardGroup
        from ..rooms import RoomType

        # `room == null || room.RoomType != RoomType.Monster` -> false.
        if rewards.room != RoomType.MONSTER:
            return
        rewards.card_rewards.append(CardRewardGroup(room_type=RoomType.MONSTER))
