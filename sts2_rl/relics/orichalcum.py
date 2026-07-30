from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Orichalcum(Relic):
    """At the end of your turn, if you have no Block, gain 6 Block."""

    id = "orichalcum"
    name = "Orichalcum"
    rarity = RelicRarity.UNCOMMON

    BLOCK = 6

    def __init__(self) -> None:
        super().__init__()
        self._should_trigger = False

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        # Orichalcum.cs:68-75 BeforeSideTurnStart clears the latch.
        self._should_trigger = False

    def on_player_turn_end_very_early(self, player: PlayerCombatState) -> None:
        """Orichalcum.cs:45-56 is BeforeSideTurnEndVeryEarly, and the source's
        own doc comment says why: it must snapshot `Block > 0` BEFORE Plating
        runs, or Plating's end-of-turn block would prevent this relic's gain.

        Hook.cs:1238-1261 runs BeforeSideTurnEndVeryEarly -> Early ->
        BeforeSideTurnEnd as three COMPLETE passes. The sim collapsed all three
        into one, so whether the snapshot saw a block-spending listener's
        effect was registration-order luck.
        """
        if player is not self.player:
            return
        if player.block > 0:
            return
        self._should_trigger = True

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        # Orichalcum.cs:58-66 BeforeSideTurnEnd grants the block.
        if not self._should_trigger:
            return
        self._should_trigger = False
        from ..cmds import BlockCmd
        BlockCmd.apply(self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED)
