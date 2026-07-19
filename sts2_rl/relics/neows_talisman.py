from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


def _basic_with_tag(deck, tag: str, last: bool = False):
    """The first (or last) Basic-rarity deck card carrying `tag`
    (Neow's Talisman picks the last Strike/Defend)."""
    from ..cards import CardRarity

    matches = [
        c for c in deck if c.rarity == CardRarity.BASIC and tag in c.tags
    ]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


@register_relic
class NeowsTalisman(Relic):
    """NeowsTalisman.cs — upgrade the deck's last basic Strike and last basic
    Defend."""

    id = "neows_talisman"
    name = "Neow's Talisman"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        for tag in ("strike", "defend"):
            card = _basic_with_tag(run.deck, tag, last=True)
            if card is not None:
                card.upgrade()
