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
        from ..cards.pool import pool_card_ids

        rares = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        count = min(self.CARDS, len(rares))
        options = [make_card(cid) for cid in run.rng.sample(rares, count)]
        for card in run.select_cards("obtain", options, 1):
            run.add_card(card)
        run.add_card(make_card("injury"))
