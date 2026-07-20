from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class FakeHappyFlower(Relic):
    """FakeHappyFlower.cs — every 5 turns, gain 1 energy (the real Happy
    Flower fires every 3). Fake Merchant knock-off, 50 gold."""

    id = "fake_happy_flower"
    name = "Fake Happy Flower"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    TURNS = 5

    def __init__(self) -> None:
        super().__init__()
        self.turns_seen = 0

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        self.turns_seen = (self.turns_seen + 1) % self.TURNS
        if self.turns_seen == 0:
            from ..cmds import EnergyCmd

            EnergyCmd.gain(self.hooks, player, 1)
