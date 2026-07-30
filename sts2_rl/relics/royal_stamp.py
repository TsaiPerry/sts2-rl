from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RoyalStamp(Relic):
    """RoyalStamp.cs — upon pickup, enchant one chosen deck card with Royally
    Approved 1, the candidate list first `UnstableShuffle`d on
    `RunState.Rng.Niche`.

    `AfterObtained` (RoyalStamp.cs:32-46) is three steps: filter the deck by
    `RoyallyApproved.CanEnchant`, `UnstableShuffle` that list on
    `base.Owner.RunState.Rng.Niche` (:36) and put it up as a
    `FromDeckForEnchantment` screen with `CardSelectorPrefs(prompt, 1)`, then
    `CardCmd.Enchant<RoyallyApproved>(cardModel, 1m)` on the pick — under
    `if (cardModel != null)`, so declining the screen enchants nothing.

    The shuffle is the order the SCREEN is built in and it happens whether or
    not the player picks, so skipping it left the Niche counter behind for
    everything downstream (relic/_off_stream_draw).
    """

    id = "royal_stamp"
    name = "Royal Stamp"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 1                      # CardsVar(1), RoyalStamp.cs:25
    AMOUNT = 1                     # CardCmd.Enchant<RoyallyApproved>(card, 1m)

    def after_obtained(self, run) -> None:
        from ..enchantments import RoyallyApprovedEnchantment, make_enchantment

        candidates = [c for c in run.deck
                      if RoyallyApprovedEnchantment.can_enchant(c)]
        if not candidates:
            return
        # `list.UnstableShuffle(RunState.Rng.Niche)` (RoyalStamp.cs:36).
        # Legacy RL play has no Niche stream, so it shuffles the shared run
        # rng exactly as every other Niche site in sts2_rl/relics does.
        if run.rng_set is not None:
            run.rng_set.niche.shuffle(candidates)
        else:
            run.rng.shuffle(candidates)
        for card in run.select_cards("enchant", candidates, self.CARDS):
            enchantment = make_enchantment("royally_approved")
            enchantment.amount = self.AMOUNT
            enchantment.attach(card)
