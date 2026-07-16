from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ArcaneScroll(Relic):
    """ArcaneScroll.cs — obtain a random Rare card (uniform, never upgraded)."""

    id = "arcane_scroll"
    name = "Arcane Scroll"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        rares = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        if rares:
            run.add_card(make_card(run.rng.choice(rares)))
