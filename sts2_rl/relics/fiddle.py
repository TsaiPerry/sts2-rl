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

    def modify_hand_draw_late(self, player: PlayerCombatState, count: int) -> int:
        # Fiddle.cs:15 is ModifyHandDraw**Late** — Hook.ModifyHandDraw runs the
        # plain pass over every listener and then a complete Late pass
        # (Hook.cs), so Fiddle's +2 lands after every plain-pass modifier
        # (Mind Rot's -1) regardless of acquisition order.
        return count + self.CARDS

    def should_draw(self, player: PlayerCombatState, from_hand_draw: bool) -> bool:
        # Only the turn-start hand draw is allowed; card-effect draws during
        # the player's own turn are prevented.
        return from_hand_draw
