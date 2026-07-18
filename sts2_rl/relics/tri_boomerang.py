from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TriBoomerang(Relic):
    """TriBoomerang.cs — upon pickup, choose 3 Instinct-eligible (Attack) deck
    cards and enchant each with Instinct (double powered-attack damage). Only
    offered by Tanx when the deck has at least 3 eligible cards."""

    id = "tri_boomerang"
    name = "Tri-Boomerang"
    rarity = RelicRarity.ANCIENT

    CARDS = 3
    # Tanx.cs GenerateInitialOptions' offer gate (_triBoomerangCount).
    MIN_ELIGIBLE = 3

    def after_obtained(self, run) -> None:
        from ..enchantments import InstinctEnchantment, make_enchantment

        candidates = [
            c for c in run.deck if InstinctEnchantment.can_enchant(c)
        ]
        for card in run.select_cards("enchant", candidates, self.CARDS):
            make_enchantment("instinct").attach(card)
