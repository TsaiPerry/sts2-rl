from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JET_DMG = 10
_PRESSURIZE_STR = 4
_PLATING = 8


class SewerClam(MachineMonster):
    """Starts with Plating 8 (and its block); alternates JET (10) and
    PRESSURIZE (+4 Strength), starting with JET."""

    min_hp = 56
    max_hp = 56

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PlatingPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)

    def build_machine(self) -> MonsterMoveStateMachine:
        pressurize = MoveState(
            "PRESSURIZE_MOVE", self._pressurize, Intent(MoveType.BUFF)
        )
        jet = MoveState(
            "JET_MOVE", self._jet, Intent(MoveType.ATTACK, damage=_JET_DMG)
        )
        pressurize.follow_up = jet
        jet.follow_up = pressurize
        return MonsterMoveStateMachine([pressurize, jet], jet)

    def _pressurize(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _PRESSURIZE_STR)

    def _jet(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _JET_DMG, 1)


SEWER_CLAM_NORMAL = Encounter(
    id="sewer_clam_normal",
    monster_classes=[SewerClam],
)
