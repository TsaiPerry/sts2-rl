from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class HeftyTablet(Relic):
    """HeftyTablet.cs — choose one of 3 random Rare cards (uniform, never
    upgraded; skippable) and gain an Injury curse."""

    id = "hefty_tablet"
    name = "Hefty Tablet"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 3

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import reward_pool_card_ids

        # HeftyTablet.cs:29 goes through CardFactory.CreateForReward, whose
        # candidate set is `options.GetPossibleCards(player)` =
        # `CardPools.SelectMany(p => p.GetUnlockedCards(...))`
        # (CardCreationOptions.cs:168-178). There is NO FilterForCombat anywhere
        # on that path — the Uniform arm only drops Basic and Ancient
        # (CardFactory.cs:221-224), which `reward_pool_card_ids` reflects. The
        # port used `pool_card_ids()`, the FilterForCombat mirror, which drops
        # `can_be_generated_in_combat = False` cards: `feed` and `not_yet`, two
        # of the strongest Rares in the pool, could never be offered, and because
        # NextItem indexes into the candidate list in pool order a 23-item list
        # returns a DIFFERENT card than a 25-item list for the same draw, so all
        # three offers diverged on every seed.
        rares = [
            cid for cid in reward_pool_card_ids(pool=run.card_pool)
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        count = min(self.CARDS, len(rares))
        # HeftyTablet.cs: CreateForReward(count) with Uniform odds = `count`
        # sequential PlayerRng.Rewards.NextItem draws, each excluding prior
        # picks (the accumulating reward blacklist).
        if run.rng_set is not None:
            pool = list(rares)
            picked = []
            for _ in range(count):
                cid = run.player_rng.rewards.next_item(pool)
                pool.remove(cid)
                picked.append(cid)
            options = [make_card(cid) for cid in picked]
        else:
            options = [make_card(cid) for cid in run.rng.sample(rares, count)]
        for card in run.select_cards("obtain", options, 1):
            run.add_card(card)
        run.add_card(make_card("injury"))
