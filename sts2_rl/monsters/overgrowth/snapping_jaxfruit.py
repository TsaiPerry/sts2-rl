from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_DMG = 3                # SnappingJaxfruit.cs:29 base
_DMG_ASC = 4            # DeadlyEnemies
_STR_GAIN = 2


class SnappingJaxfruit(Monster):
    name = "Snapping Jaxfruit"
    min_hp = 31              # SnappingJaxfruit.cs:25 base
    max_hp = 33                # SnappingJaxfruit.cs:27 base
    min_hp_asc = 34             # SnappingJaxfruit.cs:25 -- ToughEnemies
    max_hp_asc = 36             # SnappingJaxfruit.cs:27 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _DMG_ASC, _DMG)

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.ATTACK, damage=self._dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        self._execute_attack(ctx, self._dmg(), 1)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _STR_GAIN)


def _flyconid(hooks: HookSystem, rng: random.Random | None = None) -> Monster:
    from .flyconid import Flyconid
    return Flyconid(hooks, rng)


SNAPPING_JAXFRUIT_NORMAL = Encounter(
    id="snapping_jaxfruit_normal",
    monster_classes=[SnappingJaxfruit, _flyconid],
)
