from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NutritiousSoup(Relic):
    """NutritiousSoup.cs — upon pickup, enchant every Basic Strike-tagged deck
    card with Tezcatara's Ember (cost → 0, Eternal, bonus damage). Only
    offered by Tezcatara when the deck still holds a Basic Strike."""

    id = "nutritious_soup"
    name = "Nutritious Soup"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity
        from ..enchantments import TezcatarasEmberEnchantment, make_enchantment

        for card in list(run.deck):
            if (
                card.rarity == CardRarity.BASIC
                and "strike" in card.tags
                and TezcatarasEmberEnchantment.can_enchant(card)
            ):
                make_enchantment("tezcataras_ember").attach(card)
