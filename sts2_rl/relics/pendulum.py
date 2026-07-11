from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Pendulum(Relic):
    """Every 3 turns, draw 1 additional card. (The game's counter persists
    between combats; the sim's resets each combat, like Happy Flower.)"""

    id = "pendulum"
    name = "Pendulum"
    rarity = RelicRarity.COMMON

    TURNS = 3

    def __init__(self) -> None:
        super().__init__()
        self.turns_seen = 0

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        self.turns_seen = (self.turns_seen + 1) % self.TURNS
        if self.turns_seen == 0:
            from ..cmds import DrawCmd
            DrawCmd.draw(player, 1)
