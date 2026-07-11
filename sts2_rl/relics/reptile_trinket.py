from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature
    from ..potions import Potion


@register_relic
class ReptileTrinket(Relic):
    """Whenever you use a Potion, gain 3 temporary Strength (lost at the end of
    your turn)."""

    id = "reptile_trinket"
    name = "Reptile Trinket"
    rarity = RelicRarity.UNCOMMON

    STRENGTH = 3

    def on_potion_used(self, potion: Potion, target: Creature | None) -> None:
        from ..cmds import PowerCmd
        from ..powers import ReptileTrinketPower
        PowerCmd.apply(
            self.hooks, self.player, ReptileTrinketPower, self.STRENGTH,
            applier=self.player,
        )
