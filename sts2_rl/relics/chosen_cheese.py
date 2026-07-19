from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ChosenCheese(Relic):
    """ChosenCheese.cs — gain 1 Max HP whenever a combat ends (the source
    hook is AfterCombatEnd, which fires on any conclusion; a lost combat
    ends the run, so the victory path is the only one that matters).
    Granted by the Room Full of Cheese shared event."""

    id = "chosen_cheese"
    name = "Chosen Cheese"
    rarity = RelicRarity.EVENT

    MAX_HP = 1

    def on_combat_end(self, player_won: bool) -> None:
        if self.player.is_dead:
            return
        from ..cmds import CreatureCmd

        # CreatureCmd.GainMaxHp: raise the cap, then heal the same amount.
        self.player.max_hp += self.MAX_HP
        CreatureCmd.heal(self.hooks, self.player, self.MAX_HP)
