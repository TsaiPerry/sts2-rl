from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature


@register_relic
class FakeAnchor(Relic):
    """FakeAnchor.cs — start each combat with 4 Block (the real Anchor gives
    10). Fake Merchant knock-off, 50 gold."""

    id = "fake_anchor"
    name = "Fake Anchor"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    BLOCK = 4

    def on_block_cleared(self, target: Creature) -> None:
        if target is self.player and self.turn == 1:
            from ..cmds import BlockCmd

            BlockCmd.apply(
                self.hooks, self.player, self.BLOCK, props=ValueProp.UNPOWERED)
