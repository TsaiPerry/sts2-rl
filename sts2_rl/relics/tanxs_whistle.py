from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TanxsWhistle(Relic):
    """TanxsWhistle.cs — upon pickup, add a Whistle to the deck."""

    id = "tanxs_whistle"
    name = "Tanx's Whistle"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("whistle"))
