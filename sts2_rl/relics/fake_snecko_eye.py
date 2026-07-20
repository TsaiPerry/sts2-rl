from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FakeSneckoEye(Relic):
    """FakeSneckoEye.cs — all downside: you are Confused every combat (every
    drawn card's cost becomes a random 0-3) with NONE of the real Snecko
    Eye's 2 extra cards. Fake Merchant knock-off, 50 gold."""

    id = "fake_snecko_eye"
    name = "Fake Snecko Eye"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import ConfusedPower

        PowerCmd.apply(
            self.hooks, self.combat.player, ConfusedPower, 1,
            applier=self.combat.player,
        )
