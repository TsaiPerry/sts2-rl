from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Sai(Relic):
    """Sai.cs — at the start of EACH of your turns, gain 7 Block
    (BlockVar(7, Unpowered) — skips Dexterity/Frail like other relic block)."""

    id = "sai"
    name = "Sai"
    rarity = RelicRarity.ANCIENT

    BLOCK = 7

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        from ..cmds import BlockCmd

        BlockCmd.apply(
            self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED,
        )
