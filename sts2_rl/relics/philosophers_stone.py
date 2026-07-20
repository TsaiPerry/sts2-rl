from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature
    from ..player import PlayerCombatState


@register_relic
class PhilosophersStone(Relic):
    """PhilosophersStone.cs — gain 1 extra energy each turn, but every enemy
    starts with 1 Strength (AfterCreatureAddedToCombat, for creatures on the
    other side). Offered by the Darv shrine in act 3."""

    id = "philosophers_stone"
    name = "Philosopher's Stone"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    STRENGTH = 1

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def on_combat_start(self) -> None:
        from ..cmds import StrengthCmd

        for enemy in self.living_enemies():
            StrengthCmd.apply(self.hooks, enemy, self.STRENGTH)

    def on_creature_added(self, creature: Creature) -> None:
        # Creatures that join mid-fight (summons) get it too, as long as they
        # are on the other side.
        from ..cmds import StrengthCmd

        if creature is self.combat.player:
            return
        StrengthCmd.apply(self.hooks, creature, self.STRENGTH)
