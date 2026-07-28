from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LostCoffer(Relic):
    """LostCoffer.cs — a reward screen: a 3-card choice (regular base odds)
    and a potion."""

    id = "lost_coffer"
    name = "Lost Coffer"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        cards = create_reward_cards(
            run, RarityOddsType.REGULAR, mutate_pity=False,
        )
        for card in run.select_cards("card_reward", cards, 1):
            run.add_card(card)
        # PotionReward.Populate (PotionReward.cs:54-61) is
        # `PotionFactory.CreateRandomPotionOutOfCombat(player, rng)` with
        # `rng = _rngOverride ?? Player.PlayerRng.Rewards`, and LostCoffer.cs:21
        # passes no override — two Rewards draws (the rarity NextFloat then the
        # NextItem inside that band). Legacy keeps the uniform helper.
        # The PotionReward is its own declinable entry on the same screen
        # (PotionReward.OnSelect / OnSkipped), so it goes through offer_potion.
        if run.rng_set is not None:
            from ..potion_pools import generate_random_potions

            for potion in generate_random_potions(
                run.player_rng.rewards, 1, pool=run.potion_pool):
                run.offer_potion(potion)
        else:
            run.offer_potion(run.random_potion())
