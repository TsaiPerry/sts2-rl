from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Driftwood(Relic):
    """Driftwood.cs — TryModifyRewardsLate: every card reward can be rerolled
    (CardReward.CanReroll; a reroll regenerates the options once). The sim
    applies it to combat reward screens — the driver surfaces the reroll as an
    extra REWARD_CARD action."""

    id = "driftwood"
    name = "Driftwood"
    rarity = RelicRarity.ANCIENT

    def modify_combat_rewards(self, run, rewards) -> None:
        if rewards.cards:
            rewards.can_reroll = True
