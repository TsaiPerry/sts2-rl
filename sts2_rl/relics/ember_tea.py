from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class EmberTea(Relic):
    """EmberTea.cs — gain 2 Strength at the start of each of your next 5
    combats. The source hooks AfterRoomEntered on a CombatRoom (i.e. before
    the fight begins), spending one charge per combat. Bought at the Tea
    Master event for 150 gold."""

    id = "ember_tea"
    name = "Ember Tea"
    rarity = RelicRarity.EVENT

    COMBATS = 5
    STRENGTH = 2

    def __init__(self) -> None:
        super().__init__()
        self.combats_left = self.COMBATS

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => CombatsLeft <= 0
        return self.combats_left <= 0

    def on_combat_start(self) -> None:
        if self.is_used_up:
            return
        from ..cmds import StrengthCmd

        StrengthCmd.apply(self.hooks, self.combat.player, self.STRENGTH)
        self.combats_left -= 1
