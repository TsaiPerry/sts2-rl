from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SwordOfJade(Relic):
    """Evolved form of Sword of Stone (never granted directly — Sword of
    Stone replaces itself with this after 5 elite victories).

    Source: SwordOfJade.cs — AfterRoomEntered applies DynamicVars.Strength
    (3) Strength via PowerCmd.Apply<StrengthPower> whenever the entered room
    is a CombatRoom. The sim fires on_combat_start for every combat room
    type, so the hook maps there (like Vajra).
    """

    id = "sword_of_jade"
    name = "Sword of Jade"
    rarity = RelicRarity.EVENT
    STRENGTH = 3  # PowerVar<StrengthPower>(3)

    def on_combat_start(self) -> None:
        from ..cmds import PowerCmd
        from ..powers import StrengthPower

        PowerCmd.apply(
            self.hooks, self.player, StrengthPower, self.STRENGTH,
            applier=self.player,
        )
