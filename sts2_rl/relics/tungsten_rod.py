from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class TungstenRod(Relic):
    """Whenever you would lose HP, lose 1 less.

    Source: TungstenRod.cs — ModifyHpLostAfterOsty: max(0, amount - 1) for
    the owner. Hook.ModifyHpLost dispatches over the run state
    (CreatureCmd.cs), so both combat damage (modify_hp_lost) and
    out-of-combat event HP loss (modify_run_hp_loss via RunState.lose_hp)
    are reduced."""

    id = "tungsten_rod"
    name = "Tungsten Rod"
    rarity = RelicRarity.RARE

    REDUCTION = 1  # HpLossReduction(1)

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        if target is self.player:
            return max(0, amount - self.REDUCTION)
        return amount

    def modify_run_hp_loss(self, run, amount: int) -> int:
        return max(0, amount - self.REDUCTION)
