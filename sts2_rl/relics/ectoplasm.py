from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Ectoplasm(Relic):
    """Ectoplasm.cs — gain 1 extra energy each turn, but you can never gain
    gold again (ModifyGoldGained returns 0). Offered by the Darv shrine in
    act 2."""

    id = "ectoplasm"
    name = "Ectoplasm"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def modify_gold_gained(self, run, amount: float) -> float:
        return 0
