from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Fiddle(Relic):
    """Fiddle.cs — draw 2 extra cards at the start of each turn
    (ModifyHandDrawLate, CardsVar(2)), but you CANNOT draw cards during your
    turn (ShouldDraw returns false for non-hand-draw draws on your side)."""

    id = "fiddle"
    name = "Fiddle"
    rarity = RelicRarity.ANCIENT

    CARDS = 2

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        return count + self.CARDS

    def should_draw(self, player: PlayerCombatState, from_hand_draw: bool) -> bool:
        # Only the turn-start hand draw is allowed; card-effect draws during
        # the player's own turn are prevented.
        return from_hand_draw
