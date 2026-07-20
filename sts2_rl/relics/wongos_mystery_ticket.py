from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WongosMysteryTicket(Relic):
    """WongosMysteryTicket.cs — after 5 combats, the next combat's reward
    screen pays out 3 extra relics, and the ticket is spent.

    Source: AfterCombatEnd counts combats; TryModifyRewards adds
    RepeatVar(3) RelicRewards to a CombatRoom's rewards once the countdown
    hits 0, and AfterModifyingRewards marks GaveRelic (IsUsedUp). Bought
    from the mystery box at Welcome to Wongo's for 300 gold."""

    id = "wongos_mystery_ticket"
    name = "Wongo's Mystery Ticket"
    rarity = RelicRarity.EVENT

    COMBATS_TO_ACTIVATE = 5
    RELIC_COUNT = 3

    def __init__(self) -> None:
        super().__init__()
        self.combats_finished = 0
        self.gave_relic = False

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => GaveRelic
        return self.gave_relic

    def after_combat_end(self, run, room_type) -> None:
        self.combats_finished += 1

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rooms import RoomType

        if self.gave_relic or rewards.room_type not in (
            RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS,
        ):
            return
        if self.combats_finished < self.COMBATS_TO_ACTIVATE:
            return
        # RelicReward(player): three grab-bag relics, granted with the screen
        # like Lava Rock's boss relics.
        for _ in range(self.RELIC_COUNT):
            relic = run.pull_relic_from_front()
            if relic is None:
                break
            run.add_relic(relic)
            rewards.relics.append(relic)
        self.gave_relic = True
