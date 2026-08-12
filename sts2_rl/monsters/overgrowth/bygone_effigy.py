from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# Sequence: SLEEP → WAKE (10 Strength) → SLASHES (loops)
_SLASH_DMG = 13         # BygoneEffigy.cs:30 base
_SLASH_DMG_ASC = 15     # DeadlyEnemies (asc 9+)
_WAKE_STR = 10


class BygoneEffigy(Monster):
    name = "Bygone Effigy"
    min_hp = 127
    max_hp = 127
    # BygoneEffigy.cs:26-28 -- MinInitialHp = GetValueIfAscension(ToughEnemies,
    # 132, 127); MaxInitialHp reads MinInitialHp (single fixed value both ways).
    min_hp_asc = 132
    max_hp_asc = 132

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SlowPower
        PowerCmd.apply(hooks, self, SlowPower, 1)
        self._move_key = "SLEEP"

    def _slash_dmg(self) -> int:
        """BygoneEffigy.cs:30 `SlashDamage` -- re-read at both the telegraphed
        Intent (current_intent) and the executed attack (take_turn)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLASH_DMG_ASC, _SLASH_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SLEEP":
            return Intent(MoveType.SLEEP)
        if self._move_key == "WAKE":
            from ...powers import StrengthPower
            return Intent(MoveType.BUFF, buffs=[(StrengthPower, _WAKE_STR)])
        return Intent(MoveType.ATTACK, damage=self._slash_dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SLEEP":
            self._move_key = "WAKE"
        elif self._move_key == "WAKE":
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _WAKE_STR)
            self._move_key = "SLASHES"
        else:
            self._execute_attack(ctx, self._slash_dmg(), 1)


BYGONE_EFFIGY_ELITE = Encounter(
    id="bygone_effigy_elite",
    monster_classes=[BygoneEffigy],
)
