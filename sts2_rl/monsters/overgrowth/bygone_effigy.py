from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# Sequence: SLEEP → WAKE (10 Strength) → SLASHES (loops)
_SLASH_DMG = 13
_WAKE_STR = 10


class BygoneEffigy(Monster):
    min_hp = 127
    max_hp = 127

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SlowPower
        PowerCmd.apply(hooks, self, SlowPower, 1)
        self._move_key = "SLEEP"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SLEEP":
            return Intent(MoveType.BUFF, buffs=[])
        if self._move_key == "WAKE":
            from ...powers import StrengthPower
            return Intent(MoveType.BUFF, buffs=[(StrengthPower, _WAKE_STR)])
        return Intent(MoveType.ATTACK, damage=_SLASH_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SLEEP":
            self._move_key = "WAKE"
        elif self._move_key == "WAKE":
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _WAKE_STR)
            self._move_key = "SLASHES"
        else:
            self._execute_attack(ctx, _SLASH_DMG, 1)


BYGONE_EFFIGY_ELITE = Encounter(
    id="bygone_effigy_elite",
    monster_classes=[BygoneEffigy],
)
