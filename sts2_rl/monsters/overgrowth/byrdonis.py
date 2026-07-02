from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PECK_DMG = 3
_PECK_HITS = 3
_SWOOP_DMG = 17


class Byrdonis(Monster):
    min_hp = 81
    max_hp = 84

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import TerritorialPower
        PowerCmd.apply(hooks, self, TerritorialPower, 1)
        self._move_key = "SWOOP"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SWOOP":
            return Intent(MoveType.ATTACK, damage=_SWOOP_DMG)
        return Intent(MoveType.ATTACK, damage=_PECK_DMG, hits=_PECK_HITS)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "SWOOP":
            self._execute_attack(ctx, _SWOOP_DMG, 1)
            self._move_key = "PECK"
        else:
            self._execute_attack(ctx, _PECK_DMG, _PECK_HITS)
            self._move_key = "SWOOP"


BYRDONIS_ELITE = Encounter(
    id="byrdonis_elite",
    monster_classes=[Byrdonis],
)
