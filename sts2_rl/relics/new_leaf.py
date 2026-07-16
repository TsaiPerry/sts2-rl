from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NewLeaf(Relic):
    """NewLeaf.cs — transform a chosen card."""

    id = "new_leaf"
    name = "New Leaf"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for card in run.select_cards("transform", run.transformable_cards(), 1):
            run.transform_card(card)
