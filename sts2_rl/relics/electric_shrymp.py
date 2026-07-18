from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ElectricShrymp(Relic):
    """ElectricShrymp.cs — upon pickup, choose 1 deck card eligible for the
    Imbued enchantment and enchant it (CardSelectCmd.FromDeckForEnchantment)."""

    id = "electric_shrymp"
    name = "Electric Shrymp"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..enchantments import ImbuedEnchantment, make_enchantment

        candidates = [c for c in run.deck if ImbuedEnchantment.can_enchant(c)]
        for card in run.select_cards("enchant", candidates, 1):
            make_enchantment("imbued").attach(card)
