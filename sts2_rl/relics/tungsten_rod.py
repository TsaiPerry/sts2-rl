from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class TungstenRod(Relic):
    """Whenever you would lose HP, lose 1 less."""

    id = "tungsten_rod"
    name = "Tungsten Rod"
    rarity = RelicRarity.RARE

    REDUCTION = 1

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
