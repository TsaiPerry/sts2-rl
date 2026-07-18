from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PaelsHorn(Relic):
    """PaelsHorn.cs — upon pickup, add 2 Relax cards to the deck."""

    id = "paels_horn"
    name = "Pael's Horn"
    rarity = RelicRarity.ANCIENT

    CARDS = 2

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        for _ in range(self.CARDS):
            run.add_card(make_card("relax"))
