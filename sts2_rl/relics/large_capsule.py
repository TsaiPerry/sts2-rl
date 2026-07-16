from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LargeCapsule(Relic):
    """LargeCapsule.cs — obtain 2 grab-bag relics; add a Strike and a Defend
    to the deck."""

    id = "large_capsule"
    name = "Large Capsule"
    rarity = RelicRarity.ANCIENT
    RELICS = 2

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        for _ in range(self.RELICS):
            run.obtain_relic_from_grab_bag()
        run.add_card(make_card("strike"))
        run.add_card(make_card("defend"))
