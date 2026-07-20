from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PandorasBox(Relic):
    """PandorasBox.cs — upon pickup, transform EVERY basic Strike and Defend
    in your deck (CardModel.IsBasicStrikeOrDefend and IsRemovable).
    Replacements are not upgraded. Offered by the Darv shrine."""

    id = "pandoras_box"
    name = "Pandora's Box"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity

        # CardModel.IsBasicStrikeOrDefend: Basic rarity with the strike or
        # defend tag (the same test the Spiral enchantment uses).
        targets = [
            c for c in run.removable_cards()
            if c.rarity == CardRarity.BASIC
            and ("strike" in c.tags or "defend" in c.tags)
        ]
        for card in targets:
            run.transform_card(card)
