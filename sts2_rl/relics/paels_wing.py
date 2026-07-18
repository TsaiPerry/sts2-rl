from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PaelsWing(Relic):
    """PaelsWing.cs — every card reward offers a SACRIFICE alternative
    (TryModifyCardRewardAlternatives): forgo the cards; every 2nd sacrifice
    (DynamicVar "Sacrifices" = 2) obtains the next relic from the grab bag."""

    id = "paels_wing"
    name = "Pael's Wing"
    rarity = RelicRarity.ANCIENT

    SACRIFICES_PER_RELIC = 2

    def __init__(self) -> None:
        super().__init__()
        self.rewards_sacrificed = 0

    def modify_combat_rewards(self, run, rewards) -> None:
        if rewards.cards:
            rewards.sacrifice_relic = self

    def on_sacrifice(self, run) -> None:
        """OnSacrifice: count it; every SACRIFICES_PER_RELIC-th pulls the next
        grab-bag relic (RelicFactory.PullNextRelicFromFront + Obtain)."""
        self.rewards_sacrificed += 1
        if self.rewards_sacrificed % self.SACRIFICES_PER_RELIC == 0:
            run.obtain_relic_from_grab_bag()
