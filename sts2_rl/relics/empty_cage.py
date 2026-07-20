from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class EmptyCage(Relic):
    """EmptyCage.cs — upon pickup, remove 2 chosen cards from your deck.
    Offered by the Darv shrine."""

    id = "empty_cage"
    name = "Empty Cage"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    CARDS = 2

    def after_obtained(self, run) -> None:
        run.remove_cards(
            run.select_cards("remove", run.removable_cards(), self.CARDS))
