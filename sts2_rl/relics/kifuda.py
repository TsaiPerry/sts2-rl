from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Kifuda(Relic):
    """Kifuda.cs — upon pickup, enchant up to 3 deck cards with Adroit 3."""

    id = "kifuda"
    name = "Kifuda"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3           # CanonicalVars: CardsVar(3)
    ADROIT_AMOUNT = 3   # Kifuda.cs:36 -- a literal 3m, not a var

    def after_obtained(self, run) -> None:
        """Kifuda.cs:24-37 — the same shape as Gnarled Hammer with a different
        enchantment. Adroit has no CanEnchantCardType override, so the base
        CanEnchant (no Status/Curse/Quest, playable, not already enchanted) is
        the whole filter."""
        from ..enchantments import AdroitEnchantment, make_enchantment

        candidates = [c for c in run.deck if AdroitEnchantment.can_enchant(c)]
        for card in run.select_cards("enchant", candidates, self.CARDS):
            enchantment = make_enchantment("adroit")
            enchantment.amount = self.ADROIT_AMOUNT
            enchantment.attach(card)
