from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class BloodVial(Relic):
    """At the start of combat, heal 2 HP."""

    id = "blood_vial"
    name = "Blood Vial"
    rarity = RelicRarity.COMMON

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, player, 2)
