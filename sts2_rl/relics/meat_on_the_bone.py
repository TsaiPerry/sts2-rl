from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MeatOnTheBone(Relic):
    """At the end of combat, if your HP is at or below 50%, heal 12 HP."""

    id = "meat_on_the_bone"
    name = "Meat on the Bone"
    rarity = RelicRarity.RARE

    HP_THRESHOLD_PCT = 50
    HEAL = 12

    def on_combat_end(self, player_won: bool) -> None:
        if not player_won or self.player.is_dead:
            return
        threshold = self.player.max_hp * self.HP_THRESHOLD_PCT // 100
        if self.player.hp <= threshold:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, self.HEAL)
