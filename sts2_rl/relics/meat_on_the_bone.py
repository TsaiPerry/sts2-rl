from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MeatOnTheBone(Relic):
    """At the end of combat, if your HP is at or below 50%, heal 12 HP.

    MeatOnTheBone.cs:47 overrides AfterCombatVictoryEARLY, and it is the only
    override of that hook anywhere under src/Core/Models. Hook.AfterCombatVictory
    (Hook.cs:340-351) makes the Early pass over every listener BEFORE the plain
    one, so the 50% test always reads the HP the fight ended on — never one
    Burning Blood (AfterCombatVictory, +6) has already raised. At 38/80 that is
    the difference between healing (56) and not (44).
    """

    id = "meat_on_the_bone"
    name = "Meat on the Bone"
    rarity = RelicRarity.RARE

    HP_THRESHOLD_PCT = 50
    HEAL = 12

    def on_combat_victory_early(self) -> None:
        if self.player.is_dead:
            return
        threshold = self.player.max_hp * self.HP_THRESHOLD_PCT // 100
        if self.player.hp <= threshold:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, self.HEAL)
