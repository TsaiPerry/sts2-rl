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

    def on_combat_start_late(self) -> None:
        # PetrifiedToad.cs:16 is BeforeCombatStart**Late**, the second complete
        # pass of Hook.BeforeCombatStart — so the rock is procured after every
        # plain-pass listener has had its combat-start slot, which is what
        # keeps it behind Belt Buckle's belt-widening regardless of the order
        # the two relics were acquired in.
        from ..potions import PotionShapedRock
        self.player.add_potion(PotionShapedRock())
