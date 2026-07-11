from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class HappyFlower(Relic):
    """Every 3 turns, gain 1 energy. (The game's counter persists between
    combats; the sim's resets each combat.)"""

    id = "happy_flower"
    name = "Happy Flower"
    rarity = RelicRarity.COMMON

    TURNS = 3

    def __init__(self) -> None:
        super().__init__()
        self.turns_seen = 0

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        self.turns_seen = (self.turns_seen + 1) % self.TURNS
        if self.turns_seen == 0:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, 1)
