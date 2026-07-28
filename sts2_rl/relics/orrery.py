from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Orrery(Relic):
    """Orrery.cs:19-28 — upon pickup, `RewardsCmd.OfferCustom` presents
    `DynamicVars.Cards.IntValue == 5` CardRewards of 3 options each, built from
    `CardCreationOptions(character pool, CardCreationSource.Other,
    CardRarityOddsType.RegularEncounter)`.

    Source.Other, so RollForRarity uses the NON-mutating base odds (the pity
    only moves for CardCreationSource.Encounter) — the `mutate_pity=False`
    arm of create_reward_cards. No `WithSkippingDisallowed`, so each of the
    five screens is independently declinable; RewardsSet.GenerateWithoutOffering
    populates all five before offering any."""

    id = "orrery"
    name = "Orrery"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 5   # CardsVar(5) — the number of 3-card screens

    def after_obtained(self, run) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        screens = [
            create_reward_cards(run, RarityOddsType.REGULAR, mutate_pity=False)
            for _ in range(self.CARDS)
        ]
        for options in screens:
            for card in run.select_cards("card_reward", options, 1):
                run.add_card(card)
