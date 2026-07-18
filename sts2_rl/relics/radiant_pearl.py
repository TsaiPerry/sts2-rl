from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class RadiantPearl(Relic):
    """RadiantPearl.cs — at the start of combat (BeforeHandDraw, turn 1), add
    a Luminesce to your hand (CardsVar(1))."""

    id = "radiant_pearl"
    name = "Radiant Pearl"
    rarity = RelicRarity.ANCIENT

    CARDS = 1

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cards import make_card
        from ..cmds import CardPileCmd

        for _ in range(self.CARDS):
            CardPileCmd.add_to_hand(self.hooks, player, make_card("luminesce"))
