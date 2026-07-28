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
            cid for cid in pool_card_ids(pool=run.card_pool)
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        if rares:
            # ArcaneScroll.cs: CreateForReward with Uniform odds = one
            # PlayerRng.Rewards.NextItem over the Rare pool (NoUpgradeRoll, so
            # no rarity/upgrade draws).
            if run.rng_set is not None:
                pick = run.player_rng.rewards.next_item(rares)
            else:
                pick = run.rng.choice(rares)
            run.add_card(make_card(pick))
