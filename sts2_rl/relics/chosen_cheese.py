from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ChosenCheese(Relic):
    """ChosenCheese.cs:16 — gain 1 Max HP on Hook.AfterCombatEnd.

    AfterCombatEnd is NOT "any conclusion": EndCombatInternal fires it
    (CombatManager.cs:988) and ProcessPendingLoss fires nothing at all, so the
    victory path is the only dispatch there is. Granted by the Room Full of
    Cheese shared event."""

    id = "chosen_cheese"
    name = "Chosen Cheese"
    rarity = RelicRarity.EVENT

    MAX_HP = 1

    def on_combat_end(self) -> None:
        # No IsDead guard in the source (:16-20), and none is needed:
        # ReviveBeforeCombatEnd (:986) runs first, so the owner is alive by
        # the time any AfterCombatEnd listener sees them.
        from ..cmds import CreatureCmd

        # CreatureCmd.GainMaxHp: raise the cap, then heal the same amount.
        self.player.max_hp += self.MAX_HP
        CreatureCmd.heal(self.hooks, self.player, self.MAX_HP)
