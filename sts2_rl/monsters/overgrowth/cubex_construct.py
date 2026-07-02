from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# Sequence: CHARGE_UP → RB → RB → EXPEL → RB → RB → EXPEL → ...
_CYCLE_AFTER_CHARGE = ["RB", "RB", "EXPEL"]
_RB_DMG = 7
_RB_STR = 2
_EXPEL_DMG = 5
_EXPEL_HITS = 2
_CHARGE_STR = 2
_START_BLOCK = 13


class CubexConstruct(Monster):
    min_hp = 65
    max_hp = 65

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import ArtifactPower
        BlockCmd.apply(hooks, self, _START_BLOCK)
        PowerCmd.apply(hooks, self, ArtifactPower, 1)
        self._move_key = "CHARGE_UP"
        self._cycle_step = 0

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "CHARGE_UP":
            from ...powers import StrengthPower
            return Intent(MoveType.BUFF, buffs=[(StrengthPower, _CHARGE_STR)])
        if self._move_key == "RB":
            return Intent(MoveType.ATTACK, damage=_RB_DMG, also=(MoveType.BUFF,))
        return Intent(MoveType.ATTACK, damage=_EXPEL_DMG, hits=_EXPEL_HITS)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        if self._move_key == "CHARGE_UP":
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _CHARGE_STR)
            self._move_key = "RB"
            self._cycle_step = 0
        elif self._move_key == "RB":
            self._execute_attack(ctx, _RB_DMG, 1)
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _RB_STR)
            self._cycle_step += 1
            self._move_key = _CYCLE_AFTER_CHARGE[self._cycle_step % 3]
        else:  # EXPEL
            self._execute_attack(ctx, _EXPEL_DMG, _EXPEL_HITS)
            self._cycle_step += 1
            self._move_key = _CYCLE_AFTER_CHARGE[self._cycle_step % 3]


CUBEX_CONSTRUCT_NORMAL = Encounter(
    id="cubex_construct_normal",
    monster_classes=[CubexConstruct],
)
