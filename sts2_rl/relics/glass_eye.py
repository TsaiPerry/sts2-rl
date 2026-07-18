from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class GlassEye(Relic):
    """GlassEye.cs — upon pickup, a reward screen of five 3-card choices from
    the character pool: two Common, two Uncommon, one Rare (each a uniform
    in-rarity pick, never upgraded — ForNonCombatWithUniformOdds +
    NoRarityModification). Each choice is skippable."""

    id = "glass_eye"
    name = "Glass Eye"
    rarity = RelicRarity.ANCIENT

    CHOICES = 3

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        pool = pool_card_ids()
        for rarity in (
            CardRarity.COMMON, CardRarity.COMMON,
            CardRarity.UNCOMMON, CardRarity.UNCOMMON,
            CardRarity.RARE,
        ):
            matching = [
                cid for cid in pool if _CARD_CLASSES[cid].rarity == rarity
            ]
            count = min(self.CHOICES, len(matching))
            if count == 0:
                continue
            options = [make_card(cid) for cid in run.rng.sample(matching, count)]
            for card in run.select_cards("card_reward", options, 1):
                run.add_card(card)
