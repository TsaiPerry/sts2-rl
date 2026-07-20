from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class FakeOrichalcum(Relic):
    """FakeOrichalcum.cs — at the end of your turn, if you have no Block,
    gain 3 Block (the real Orichalcum gives 6). Fake Merchant knock-off, 50
    gold."""

    id = "fake_orichalcum"
    name = "Fake Orichalcum"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    BLOCK = 3

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if player.block == 0:
            from ..cmds import BlockCmd

            BlockCmd.apply(
                self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED)
