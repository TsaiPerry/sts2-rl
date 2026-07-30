from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LavaRock(Relic):
    """LavaRock.cs — the first act's boss rewards include 2 extra relics
    (grab-bag pulls); one-shot."""

    id = "lava_rock"
    name = "Lava Rock"
    rarity = RelicRarity.ANCIENT
    RELICS = 2

    def __init__(self) -> None:
        super().__init__()
        self.has_triggered = False

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rooms import RoomType

        if (
            self.has_triggered
            # LavaRock.cs `room == null || room.RoomType != Boss`.
            or rewards.room != RoomType.BOSS
            or run.act_index != 0
        ):
            return
        for _ in range(self.RELICS):
            relic = run.pull_relic_from_front()
            if relic is None:
                break
            # RelicReward is take-or-skip (RelicReward.cs:109-123).
            run.offer_relic(relic)
            rewards.relics.append(relic)
        self.has_triggered = True
