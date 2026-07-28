from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Cauldron(Relic):
    """Cauldron.cs — upon pickup, `RewardsCmd.OfferCustom` presents FIVE
    PotionRewards, each of which the player may take or decline.

    Cauldron.cs:31-55 builds `DynamicVars["Potions"].IntValue == 5` rewards;
    the shipping arm is `new PotionReward(base.Owner)` ×5 (the fixed
    Flex/Weak/Vulnerable/Strength/Dexterity list at :16-23 is the TestMode
    arm). Each PotionReward.Populate is
    `PotionFactory.CreateRandomPotionOutOfCombat(player, rng)` off
    PlayerRng.Rewards, and each is its own declinable entry, so the five run
    through run.offer_potion (the take-or-skip seam `relic/_auto_keep`
    named)."""

    id = "cauldron"
    name = "Cauldron"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    POTIONS = 5  # DynamicVar("Potions", 5)

    def after_obtained(self, run) -> None:
        if run.rng_set is not None:
            from ..potion_pools import generate_random_potion

            # Five independent PotionRewards, each populated by its own
            # CreateRandomPotionOutOfCombat (two Rewards draws apiece) — the
            # blacklist is per-reward, so ids may repeat.
            potions = [
                generate_random_potion(
                    run.player_rng.rewards, pool=run.potion_pool)
                for _ in range(self.POTIONS)
            ]
        else:
            potions = [run.random_potion() for _ in range(self.POTIONS)]
        for potion in potions:
            run.offer_potion(potion)
