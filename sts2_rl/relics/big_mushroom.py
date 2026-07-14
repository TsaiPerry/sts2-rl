from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BigMushroom(Relic):
    """Raise Max HP by 20 on pickup; draw 2 fewer cards on the first turn of
    each combat.

    Source: BigMushroom.cs — AfterObtained gains 20 Max HP; ModifyHandDraw
    subtracts 2 on turn 1 (plus a purely-cosmetic size increase). Granted by the
    Hungry for Mushrooms event. The +20 Max HP pickup is applied by the event
    (RunState has no run-level AfterObtained dispatch)."""

    id = "big_mushroom"
    name = "Big Mushroom"
    rarity = RelicRarity.EVENT

    MAX_HP = 20
    DRAW_REDUCTION = 2

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        if self.turn == 1:
            return count - self.DRAW_REDUCTION
        return count
