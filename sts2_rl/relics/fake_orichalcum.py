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

    def __init__(self) -> None:
        super().__init__()
        self._should_trigger = False

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        self._should_trigger = False

    def on_player_turn_end_very_early(self, player: PlayerCombatState) -> None:
        # FakeOrichalcum.cs:46 is BeforeSideTurnEndVeryEarly, the identical
        # two-phase shape as the real Orichalcum: snapshot `Block > 0` before
        # Plating can grant block, then grant in the plain pass (:60).
        if player is self.player and player.block == 0:
            self._should_trigger = True

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if not self._should_trigger:
            return
        self._should_trigger = False
        from ..cmds import BlockCmd

        BlockCmd.apply(
            self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED)
