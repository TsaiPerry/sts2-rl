from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TinyMailbox(Relic):
    """TinyMailbox.cs — resting adds two PotionRewards to the rest-heal
    reward screen (TryModifyRestSiteHealRewards), each an independent
    take-or-skip offer like Punch-Off's fight purse."""

    id = "tiny_mailbox"
    name = "Tiny Mailbox"
    rarity = RelicRarity.UNCOMMON

    POTIONS = 2

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
        # PotionReward.Populate rolls on the per-player Rewards stream in the
        # parity path (rewards.generate_combat_rewards does the same); the
        # legacy RL path keeps run.random_potion's shared draw.
        for _ in range(self.POTIONS):
            if run.rng_set is not None:
                from ..potion_pools import generate_random_potion
                rewards.special_potions.append(
                    generate_random_potion(run.rewards_rng))
            else:
                rewards.special_potions.append(run.random_potion())
