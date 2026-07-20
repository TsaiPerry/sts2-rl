from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class FakeVenerableTeaSet(Relic):
    """FakeVenerableTeaSet.cs — on the first turn of a combat that follows a
    Rest, gain 1 energy (the real Venerable Tea Set gives 2). Whether you
    rested is out-of-combat state, injected via the constructor like the real
    one. Fake Merchant knock-off, 50 gold."""

    id = "fake_venerable_tea_set"
    name = "Fake Venerable Tea Set"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    ENERGY = 1

    def __init__(self, rested: bool = False) -> None:
        super().__init__()
        self._pending = rested

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        if self._pending:
            self._pending = False
            from ..cmds import EnergyCmd

            EnergyCmd.gain(self.hooks, player, self.ENERGY)
