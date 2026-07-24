from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Claws(Relic):
    """Claws.cs — upon pickup, choose up to 6 deck cards (CardsVar(6),
    skippable) and transform EACH into a Maul, carrying over upgrade and
    enchantment (CreateMaulFromOriginal).

    The screen is `CardSelectorPrefs(prompt, 0, 6)` — MinSelect **0** with
    RequireManualConfirmation — so confirming with fewer than 6 (or zero) cards
    picked is legal; "transform_optional" is the skippable purpose for that."""

    id = "claws"
    name = "Claws"
    rarity = RelicRarity.ANCIENT

    CARDS = 6

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        candidates = run.removable_cards()
        for original in run.select_cards(
                "transform_optional", candidates, self.CARDS):
            maul = make_card("maul")
            if original.upgrade_level > 0 and maul.is_upgradable:
                maul.upgrade()
            if original.enchantment is not None:
                enchantment = original.enchantment
                original.enchantment = None
                enchantment.card = None
                if enchantment.can_enchant(maul):
                    enchantment.attach(maul)
            run.transform_card(original, into=maul)
