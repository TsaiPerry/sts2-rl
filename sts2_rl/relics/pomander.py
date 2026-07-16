from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Pomander(Relic):
    """Pomander.cs — upgrade a chosen card."""

    id = "pomander"
    name = "Pomander"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for card in run.select_cards("upgrade", run.upgradable_cards(), 1):
            card.upgrade()
