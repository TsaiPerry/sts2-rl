from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_DMG = 3
_STR_GAIN = 2


class SnappingJaxfruit(Monster):
    min_hp = 31
    max_hp = 33

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.ATTACK, damage=_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        self._execute_attack(ctx, _DMG, 1)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _STR_GAIN)


def _flyconid(hooks: HookSystem, rng: random.Random | None = None) -> Monster:
    from .flyconid import Flyconid
    return Flyconid(hooks, rng)


SNAPPING_JAXFRUIT_NORMAL = Encounter(
    id="snapping_jaxfruit_normal",
    monster_classes=[SnappingJaxfruit, _flyconid],
)
