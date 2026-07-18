from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PaelsClaw(Relic):
    """PaelsClaw.cs — upon pickup, enchant EVERY Goopy-eligible deck card
    (Defend-tagged) with Goopy (amount 1). Only offered by Pael when the deck
    has at least 3 eligible cards."""

    id = "paels_claw"
    name = "Pael's Claw"
    rarity = RelicRarity.ANCIENT

    # Pael.cs GenerateInitialOptions' offer gate.
    MIN_ELIGIBLE = 3

    def after_obtained(self, run) -> None:
        from ..enchantments import GoopyEnchantment, make_enchantment

        for card in list(run.deck):
            if GoopyEnchantment.can_enchant(card):
                make_enchantment("goopy").attach(card)
