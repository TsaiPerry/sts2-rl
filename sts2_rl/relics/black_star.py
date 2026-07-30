from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class BlackStar(Relic):
    """BlackStar.cs — elite combats drop an extra relic (TryModifyRewards
    adds a RelicReward on RoomType.Elite). Offered by the Darv shrine."""

    id = "black_star"
    name = "Black Star"
    rarity = RelicRarity.ANCIENT

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rooms import RoomType

        # BlackStar.cs `room == null || room.RoomType != Elite`.
        if rewards.room != RoomType.ELITE:
            return
        relic = run.pull_relic_from_front()
        if relic is not None:
            # RelicReward is take-or-skip (RelicReward.cs:109-123).
            run.offer_relic(relic)
            rewards.relics.append(relic)
