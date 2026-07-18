from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class PaelsGrowth(Relic):
    """PaelsGrowth.cs — upon pickup, enchant 1 chosen deck card with Clone
    (amount 4); adds the Clone rest-site option (CloneRestSiteOption:
    duplicate every Clone-enchanted deck card)."""

    id = "paels_growth"
    name = "Pael's Growth"
    rarity = RelicRarity.ANCIENT

    CLONE_AMOUNT = 4

    def after_obtained(self, run) -> None:
        from ..enchantments import CloneEnchantment, make_enchantment

        candidates = [c for c in run.deck if CloneEnchantment.can_enchant(c)]
        for card in run.select_cards("enchant", candidates, 1):
            enchantment = make_enchantment("clone")
            enchantment.amount = self.CLONE_AMOUNT
            enchantment.attach(card)

    def modify_rest_site_options(self, run, options) -> None:
        def clone(run) -> None:
            # CloneRestSiteOption.OnSelect: duplicate every Clone-enchanted
            # deck card. CloneCard uses ClonePreservingMutability — a full
            # copy INCLUDING the enchantment, so each copy is itself
            # Clone-enchanted (repeated use doubles the set).
            from ..cards import make_card
            from ..enchantments import make_enchantment

            for card in [c for c in run.deck
                         if c.enchantment is not None
                         and c.enchantment.id == "clone"]:
                copy = make_card(card.id)
                for _ in range(card.upgrade_level):
                    if copy.is_upgradable:
                        copy.upgrade()
                enchantment = make_enchantment("clone")
                enchantment.amount = card.enchantment.amount
                enchantment.attach(copy)
                run.add_card(copy)

        options.append(RestSiteOption("CLONE", clone))
