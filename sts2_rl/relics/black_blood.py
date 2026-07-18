from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class BlackBlood(Relic):
    """BlackBlood.cs — at the end of combat, heal 12 HP. Burning Blood's
    refinement, granted by Touch of Orobas."""

    id = "black_blood"
    name = "Black Blood"
    rarity = RelicRarity.STARTER

    HEAL = 12

    def on_combat_end(self, player_won: bool) -> None:
        if player_won and not self.player.is_dead:
            from ..cmds import CreatureCmd
            CreatureCmd.heal(self.hooks, self.player, self.HEAL)
