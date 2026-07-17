from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Pantograph(Relic):
    """At the start of Boss combats, heal 25 HP.

    Source: Pantograph.cs — BeforeCombatStart when the current room is
    RoomType.Boss -> CreatureCmd.Heal(HealVar(25)). Gated on the combat's
    room type (CombatState.room_type, set by the run driver); the
    map-lookahead Active status display is UI-only and not modeled."""

    id = "pantograph"
    name = "Pantograph"
    rarity = RelicRarity.UNCOMMON

    HEAL = 25  # HealVar(25)

    def on_combat_start(self) -> None:
        from ..rooms import RoomType
        if self.combat.room_type != RoomType.BOSS:
            return
        from ..cmds import CreatureCmd
        CreatureCmd.heal(self.combat.hooks, self.player, self.HEAL)
