from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature


@register_relic
class RedSkull(Relic):
    """While your HP is at or below 50%, you have 3 Strength (applied and
    removed as your HP crosses the threshold)."""

    id = "red_skull"
    name = "Red Skull"
    rarity = RelicRarity.COMMON

    HP_THRESHOLD_PCT = 50
    STRENGTH = 3

    def __init__(self) -> None:
        super().__init__()
        self._applied = False

    def _update(self) -> None:
        threshold = self.player.max_hp * self.HP_THRESHOLD_PCT // 100
        below = self.player.hp <= threshold
        if below and not self._applied:
            self._applied = True
            self._change_strength(self.STRENGTH)
        elif not below and self._applied:
            self._applied = False
            self._change_strength(-self.STRENGTH)

    def _change_strength(self, amount: int) -> None:
        from ..cmds import PowerCmd
        from ..powers import StrengthPower
        PowerCmd.apply(self.hooks, self.player, StrengthPower, amount, applier=self.player)

    def reset_for_combat(self) -> None:
        # RedSkull.AfterCombatEnd (:52-57) clears StrengthApplied; without it
        # combat 2 either never re-applies the +3 or opens by removing a
        # Strength the fresh CombatState never granted (-3).
        self._applied = False

    def on_combat_start(self) -> None:
        self._update()

    def on_hp_changed(self, creature: Creature, delta: int) -> None:
        if creature is self.player:
            self._update()
