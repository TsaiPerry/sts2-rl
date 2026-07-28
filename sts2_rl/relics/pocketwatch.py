from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class Pocketwatch(Relic):
    """If you played 3 or fewer cards during your last turn, draw 3 additional
    cards at the start of your turn (from turn 2 on)."""

    id = "pocketwatch"
    name = "Pocketwatch"
    rarity = RelicRarity.RARE

    THRESHOLD = 3
    DRAW = 3

    def __init__(self) -> None:
        super().__init__()
        self._played_this_turn = 0
        self._played_last_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self._played_this_turn += 1

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        # Pre-draw: snapshot last turn's count so modify_hand_draw can read it.
        self._played_last_turn = self._played_this_turn
        self._played_this_turn = 0

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        if self.turn == 1:
            return count
        if self._played_last_turn <= self.THRESHOLD:
            return count + self.DRAW
        return count
