from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class BagOfMarbles(Relic):
    """At the start of combat, apply 1 Vulnerable to ALL enemies."""

    id = "bag_of_marbles"
    name = "Bag of Marbles"
    rarity = RelicRarity.COMMON

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import PowerCmd
            from ..powers import VulnerablePower
            # BagOfMarbles.cs:28: PowerCmd.Apply<VulnerablePower>(...,
            # combatState.HittableEnemies, ...) -- the candidate set is
            # HittableEnemies, not "every not-dead enemy".
            for enemy in self.hittable_enemies():
                PowerCmd.apply(self.hooks, enemy, VulnerablePower, 1, applier=player)
