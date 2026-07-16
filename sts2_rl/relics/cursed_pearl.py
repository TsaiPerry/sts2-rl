from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class CursedPearl(Relic):
    """CursedPearl.cs — gain 333 gold and a Greed curse."""

    id = "cursed_pearl"
    name = "Cursed Pearl"
    rarity = RelicRarity.ANCIENT
    GOLD = 333

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("greed"))
        run.gain_gold(self.GOLD)
