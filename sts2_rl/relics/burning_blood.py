from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class BurningBlood(Relic):
    """At the end of combat, heal 6 HP (Ironclad starter)."""

    id = "burning_blood"
    name = "Burning Blood"
    rarity = RelicRarity.STARTER

    HEAL = 6

    def on_combat_end(self, player_won: bool) -> None:
        if player_won and not self.player.is_dead:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, self.HEAL)
