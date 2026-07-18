from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BlessedAntler(Relic):
    """BlessedAntler.cs — +1 max Energy (EnergyVar(1)); on turn 1
    (BeforeHandDraw) shuffle 3 Dazed into the draw pile (CardsVar(3))."""

    id = "blessed_antler"
    name = "Blessed Antler"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    DAZED = 3

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cards import make_card
        from ..cmds import CardPileCmd

        for _ in range(self.DAZED):
            CardPileCmd.add_to_draw(self.hooks, player, make_card("dazed"))
