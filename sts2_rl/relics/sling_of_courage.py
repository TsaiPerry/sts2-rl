from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SlingOfCourage(Relic):
    """At the start of Elite combats, gain 2 Strength.

    Source: SlingOfCourage.cs — AfterRoomEntered with RoomType.Elite ->
    PowerCmd.Apply<StrengthPower>(PowerVar(2)) on the owner. Gated on the
    combat's room type (CombatState.room_type, set by the run driver)."""

    id = "sling_of_courage"
    name = "Sling of Courage"
    rarity = RelicRarity.SHOP

    STRENGTH = 2  # PowerVar<StrengthPower>(2)

    def on_combat_start(self) -> None:
        from ..rooms import RoomType
        if self.combat.room_type != RoomType.ELITE:
            return
        from ..cmds import PowerCmd
        from ..powers import StrengthPower
        PowerCmd.apply(
            self.combat.hooks, self.player, StrengthPower, self.STRENGTH,
            applier=self.player,
        )
