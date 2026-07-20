from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class FakeBloodVial(Relic):
    """FakeBloodVial.cs — at the start of combat, heal 1 HP (the real Blood
    Vial heals 2). Fake Merchant knock-off, 50 gold."""

    id = "fake_blood_vial"
    name = "Fake Blood Vial"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    HEAL = 1

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import CreatureCmd

            CreatureCmd.heal(self.hooks, player, self.HEAL)
