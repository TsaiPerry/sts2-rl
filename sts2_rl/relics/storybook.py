from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Storybook(Relic):
    """Storybook.cs — upon pickup, add a Brightest Flame to the deck."""

    id = "storybook"
    name = "Storybook"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("brightest_flame"))
