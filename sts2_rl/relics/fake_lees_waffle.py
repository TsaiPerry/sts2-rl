from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FakeLeesWaffle(Relic):
    """FakeLeesWaffle.cs — upon pickup, heal 10% of Max HP (the real Lee's
    Waffle raises Max HP and heals to full). Fake Merchant knock-off, 50
    gold."""

    id = "fake_lees_waffle"
    name = "Fake Lee's Waffle"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost
    has_upon_pickup_effect = True

    HEAL_PERCENT = 10

    def after_obtained(self, run) -> None:
        run.heal(int(run.max_hp * self.HEAL_PERCENT / 100))
