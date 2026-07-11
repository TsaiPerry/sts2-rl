from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class VenerableTeaSet(Relic):
    """On the first turn of a combat that follows a Rest, gain 2 energy. Whether
    you rested is out-of-combat state (like Girya's lifts), so it is injected
    via the constructor; it defaults to False (no effect)."""

    id = "venerable_tea_set"
    name = "Venerable Tea Set"
    rarity = RelicRarity.COMMON

    ENERGY = 2

    def __init__(self, rested: bool = False) -> None:
        super().__init__()
        self._pending = rested

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        # Fires on the first energy reset of the combat (turn 1), once.
        if self._pending:
            self._pending = False
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, self.ENERGY)
