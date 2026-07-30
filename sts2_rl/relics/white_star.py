from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class WhiteStar(Relic):
    """WhiteStar.cs — an Elite's rewards carry a SECOND card choice, rolled on
    Boss odds (`TryModifyRewards` adds
    `new CardReward(CardCreationOptions.ForRoom(owner, RoomType.Boss), 3)`).

    Same shape as Prayer Wheel, and it lands in the same place:
    `CombatRewards.card_rewards` is a LIST of `CardRewardGroup`, so a second
    pick-one-of-3 has a field to live in and the driver already walks them.
    What differs from Prayer Wheel is the odds table -- `ForRoom(RoomType.Boss)`
    selects `CardRarityOddsType.BossEncounter` (CardCreationOptions.cs:122-129),
    which rewards.py maps to (1.0, 0.0, 0.0), so the extra group is three RARE
    cards rather than three Elite-tier ones."""

    id = "white_star"
    name = "White Star"
    rarity = RelicRarity.RARE

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rewards import CardRewardGroup
        from ..rooms import RoomType

        # WhiteStar.cs:24-27 -- `room == null || room.RoomType != Elite`.
        if rewards.room != RoomType.ELITE:
            return
        # Unpopulated, like Prayer Wheel's: RewardsSet.cs:137-143 draws the
        # options of a hook-added group only AFTER both ModifyRewards passes,
        # which is what puts the three Rewards-stream draws in the right place.
        rewards.card_rewards.append(CardRewardGroup(room_type=RoomType.BOSS))

    @classmethod
    def is_allowed(cls, run) -> bool:
        """WhiteStar.cs:14-17: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
