from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PetrifiedToad(Relic):
    """At the start of each combat, procure a Potion Shaped Rock.

    Source: PetrifiedToad.cs — BeforeCombatStartLate ->
    PotionCmd.TryToProcure<PotionShapedRock> (adds the potion to the first
    free belt slot; fails silently when the belt is full)."""

    id = "petrified_toad"
    name = "Petrified Toad"
    rarity = RelicRarity.UNCOMMON

    def on_combat_start(self) -> None:
        from ..potions import PotionShapedRock
        player = self.player
        if len(player.potions) < player.max_potions:
            player.potions.append(PotionShapedRock())
