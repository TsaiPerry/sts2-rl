from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FakeMango(Relic):
    """FakeMango.cs — upon pickup, raise Max HP by 3 (the real Mango gives
    14). Fake Merchant knock-off, 50 gold."""

    id = "fake_mango"
    name = "Fake Mango"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost
    has_upon_pickup_effect = True

    MAX_HP = 3

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)
