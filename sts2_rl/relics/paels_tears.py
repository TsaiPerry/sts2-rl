from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PaelsTears(Relic):
    """PaelsTears.cs — if you end your turn with unspent Energy, gain 2 Energy
    at the start of your next turn (BeforeSideTurnEnd records the leftover;
    AfterSideTurnStart grants EnergyVar(2))."""

    id = "paels_tears"
    name = "Pael's Tears"
    rarity = RelicRarity.ANCIENT

    ENERGY = 2

    def __init__(self) -> None:
        super().__init__()
        self.had_leftover_energy = False

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        self.had_leftover_energy = player.energy > 0

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.had_leftover_energy:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, self.ENERGY)
