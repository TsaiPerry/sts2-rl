from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature

@register_relic
class GremlinHorn(Relic):
    """Whenever an enemy dies, gain 1 energy and draw 1 card."""

    id = "gremlin_horn"
    name = "Gremlin Horn"
    rarity = RelicRarity.UNCOMMON

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature.side != self.player.side:
            from ..cmds import DrawCmd, EnergyCmd
            EnergyCmd.gain(self.hooks, self.player, 1)
            DrawCmd.draw(self.player, 1)
