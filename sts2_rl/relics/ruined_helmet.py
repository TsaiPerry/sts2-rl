from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature


@register_relic
class RuinedHelmet(Relic):
    """The first time you gain Strength each combat, gain twice as much."""

    id = "ruined_helmet"
    name = "Ruined Helmet"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._used = False

    def reset_for_combat(self) -> None:
        # RuinedHelmet.AfterCombatEnd (:57-61).
        self._used = False

    def modify_power_amount(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None = None,
    ) -> int:
        from ..powers import StrengthPower
        if (
            not self._used
            and power_cls is StrengthPower
            and target is self.player
            and amount > 0
        ):
            self._used = True
            return amount * 2
        return amount
