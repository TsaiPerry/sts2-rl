from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


def _basic_with_tag(deck, tag: str, last: bool = False):
    """The first (or last) Basic-rarity deck card carrying `tag`
    (Leafy Poultice transforms the first Strike/Defend)."""
    from ..cards import CardRarity

    matches = [
        c for c in deck if c.rarity == CardRarity.BASIC and tag in c.tags
    ]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


@register_relic
class LeafyPoultice(Relic):
    """LeafyPoultice.cs — lose 12 Max HP; transform a basic Strike and a
    basic Defend (the deck's first of each)."""

    id = "leafy_poultice"
    name = "Leafy Poultice"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 12

    def after_obtained(self, run) -> None:
        run.lose_max_hp(self.MAX_HP)
        for tag in ("strike", "defend"):
            card = _basic_with_tag(run.deck, tag)
            if card is not None:
                run.transform_card(card)
