from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_OIL_SPRAY_DMG = 8
_OIL_SPRAY_WEAK = 1
_SLAM_DMG = 11
_RAGE_DMG = 6
_RAGE_STR = 3


class SludgeSpinner(MachineMonster):
    """Opens with OIL_SPRAY (8 + Weak 1); afterwards picks uniformly among
    OIL_SPRAY / SLAM (11) / RAGE (6 + self 3 Str) without repeating the same
    move twice in a row."""

    min_hp = 37
    max_hp = 39

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        oil_spray = MoveState(
            "OIL_SPRAY_MOVE", self._oil_spray,
            Intent(MoveType.ATTACK, damage=_OIL_SPRAY_DMG,
                   also=(MoveType.DEBUFF,)),
        )
        slam = MoveState(
            "SLAM_MOVE", self._slam, Intent(MoveType.ATTACK, damage=_SLAM_DMG)
        )
        rage = MoveState(
            "RAGE_MOVE", self._rage,
            Intent(MoveType.ATTACK, damage=_RAGE_DMG, also=(MoveType.BUFF,)),
        )
        rand = RandomBranchState("RAND")
        oil_spray.follow_up = rand
        slam.follow_up = rand
        rage.follow_up = rand
        rand.add_branch(oil_spray, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(slam, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(rage, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        return MonsterMoveStateMachine([rand, oil_spray, slam, rage], oil_spray)

    def _oil_spray(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _OIL_SPRAY_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _OIL_SPRAY_WEAK)

    def _slam(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SLAM_DMG, 1)

    def _rage(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _RAGE_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _RAGE_STR)


SLUDGE_SPINNER_WEAK = Encounter(
    id="sludge_spinner_weak",
    monster_classes=[SludgeSpinner],
)
