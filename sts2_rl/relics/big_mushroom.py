from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class BigMushroom(Relic):
    """Raise Max HP by 20 on pickup; draw 2 fewer cards on the first turn of
    each combat.

    Source: BigMushroom.cs — AfterObtained (:24-28) gains 20 Max HP
    (MaxHpVar(20m)); ModifyHandDraw subtracts 2 on turn 1 (plus a
    purely-cosmetic Grow()). Granted by the Hungry for Mushrooms event.

    The +20 used to be applied by the EVENT, on the docstring's claim that
    "RunState has no run-level AfterObtained dispatch". That claim is false —
    `RunState.add_relic` calls `relic.after_obtained(self)`, and the sibling
    relic from the same event has always used it — so the gain now lives where
    the source puts it and reaches the relic however it is granted."""

    id = "big_mushroom"
    name = "Big Mushroom"
    rarity = RelicRarity.EVENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    MAX_HP = 20
    DRAW_REDUCTION = 2

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)      # BigMushroom.cs:26

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        if self.turn == 1:
            return count - self.DRAW_REDUCTION
        return count
