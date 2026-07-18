from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SandCastle(Relic):
    """SandCastle.cs — upon pickup, upgrade ALL upgradable cards in the deck."""

    id = "sand_castle"
    name = "Sand Castle"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for card in run.deck:
            if card.is_upgradable:
                card.upgrade()
