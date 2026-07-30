from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class BurningBlood(Relic):
    """At the end of combat, heal 6 HP (Ironclad starter)."""

    id = "burning_blood"
    name = "Burning Blood"
    rarity = RelicRarity.STARTER

    HEAL = 6

    def on_combat_victory(self) -> None:
        # BurningBlood.cs:16 is AfterCombatVictory, which only the victory path
        # dispatches (CombatManager.cs:999) -- so no `player_won` test. The
        # `IsDead` guard (:18) is the source's own and stays, even though
        # ReviveBeforeCombatEnd (:986) has already healed the owner to 1.
        if not self.player.is_dead:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, self.HEAL)
