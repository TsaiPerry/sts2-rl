from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Claws(Relic):
    """Claws.cs — upon pickup, choose up to 6 deck cards (CardsVar(6),
    skippable) and transform EACH into a Maul, carrying over upgrade and
    enchantment (CreateMaulFromOriginal)."""

    id = "claws"
    name = "Claws"
    rarity = RelicRarity.ANCIENT

    CARDS = 6

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        candidates = run.removable_cards()
        for original in run.select_cards("transform", candidates, self.CARDS):
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
