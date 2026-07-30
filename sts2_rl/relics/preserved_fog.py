from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PreservedFog(Relic):
    """PreservedFog.cs — upon pickup, choose 3 deck cards to REMOVE
    (CardsVar(3)), then add a Folly curse."""

    id = "preserved_fog"
    name = "Preserved Fog"
    rarity = RelicRarity.ANCIENT

    CARDS = 3

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        for card in run.select_cards("remove", run.removable_cards(), self.CARDS):
            run.remove_cards([card])   # CardPileCmd.RemoveFromDeck
        run.add_card(make_card("folly"))
