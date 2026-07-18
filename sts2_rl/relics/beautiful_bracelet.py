from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class BeautifulBracelet(Relic):
    """BeautifulBracelet.cs — upon pickup, choose 3 Swift-eligible deck cards
    and enchant each with Swift 3 (draw 3 the first time it's played each
    combat). Only offered by Nonupeipe when the deck has at least 4
    Swift-eligible cards."""

    id = "beautiful_bracelet"
    name = "Beautiful Bracelet"
    rarity = RelicRarity.ANCIENT

    CARDS = 3
    SWIFT_AMOUNT = 3
    # Nonupeipe.cs GenerateInitialOptions' offer gate.
    MIN_ELIGIBLE = 4

    def after_obtained(self, run) -> None:
        from ..enchantments import SwiftEnchantment, make_enchantment

        candidates = [c for c in run.deck if SwiftEnchantment.can_enchant(c)]
        for card in run.select_cards("enchant", candidates, self.CARDS):
            enchantment = make_enchantment("swift")
            enchantment.amount = self.SWIFT_AMOUNT
            enchantment.attach(card)
