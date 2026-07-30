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

    def modify_combat_rewards_late(self, run, rewards) -> None:
        # `foreach (CardReward item in rewards.OfType<CardReward>())` — EVERY
        # card group on the set, not just the first (Driftwood.cs:20-23).
        # No IsPopulated check in the source either: a group another relic
        # added in the plain pass is still empty here and still gets the flag.
        for group in rewards.card_rewards:
            group.can_reroll = True
