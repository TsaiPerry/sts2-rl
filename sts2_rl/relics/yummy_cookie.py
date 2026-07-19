from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class YummyCookie(Relic):
    """YummyCookie.cs — upon pickup, choose 4 deck cards to upgrade
    (CardSelectCmd.FromDeckForUpgrade, CardsVar(4))."""

    id = "yummy_cookie"
    name = "Yummy Cookie"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 4

    def after_obtained(self, run) -> None:
        candidates = run.upgradable_cards()
        for card in run.select_cards("upgrade", candidates, self.CARDS):
            card.upgrade()
