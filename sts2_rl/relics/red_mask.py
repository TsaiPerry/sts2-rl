from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class RedMask(Relic):
    """At the start of combat, apply 1 Weak to ALL enemies."""

    id = "red_mask"
    name = "Red Mask"
    rarity = RelicRarity.COMMON

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import PowerCmd
            from ..powers import WeakPower
            for enemy in self.living_enemies():
                PowerCmd.apply(self.hooks, enemy, WeakPower, 1, applier=player)
