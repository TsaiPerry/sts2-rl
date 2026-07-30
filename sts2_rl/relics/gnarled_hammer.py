from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class GnarledHammer(Relic):
    """GnarledHammer.cs — upon pickup, enchant up to 3 deck cards with Sharp 3."""

    id = "gnarled_hammer"
    name = "Gnarled Hammer"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3          # CanonicalVars: CardsVar(3)
    SHARP_AMOUNT = 3   # CanonicalVars: DynamicVar("SharpAmount", 3)

    def after_obtained(self, run) -> None:
        """GnarledHammer.cs:28-40 — a non-cancelable 0..3 enchant screen over
        the cards Sharp can enchant, then `CardCmd.Enchant(..., SharpAmount)`
        on each pick. `CardSelectCmd.FromDeckForEnchantment` filters by the
        enchantment's own CanEnchant, which for Sharp is Attacks only."""
        from ..enchantments import SharpEnchantment, make_enchantment

        candidates = [c for c in run.deck if SharpEnchantment.can_enchant(c)]
        for card in run.select_cards("enchant", candidates, self.CARDS):
            enchantment = make_enchantment("sharp")
            enchantment.amount = self.SHARP_AMOUNT
            enchantment.attach(card)
