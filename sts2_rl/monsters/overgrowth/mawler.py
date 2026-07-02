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

_CLAW_DMG = 4
_CLAW_HITS = 2
_RIP_DMG = 14
_VULNERABLE_AMT = 3


class Mawler(MachineMonster):
    """Starts with CLAW, then picks randomly each turn among RIP_AND_TEAR
    (no consecutive repeats), ROAR (usable once per combat), and CLAW
    (no consecutive repeats), all with equal weight."""
    min_hp = 72
    max_hp = 72

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        claw = MoveState(
            "CLAW", self._claw,
            Intent(MoveType.ATTACK, damage=_CLAW_DMG, hits=_CLAW_HITS),
        )
        rip = MoveState(
            "RIP_AND_TEAR", self._rip, Intent(MoveType.ATTACK, damage=_RIP_DMG)
        )
        roar = MoveState("ROAR", self._roar, self._roar_intent)
        branch = RandomBranchState("BRANCH")
        branch.add_branch(rip, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(roar, repeat_type=MoveRepeatType.USE_ONLY_ONCE)
        branch.add_branch(claw, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        claw.follow_up = branch
        rip.follow_up = branch
        roar.follow_up = branch
        return MonsterMoveStateMachine([claw, rip, roar, branch], claw)

    @staticmethod
    def _roar_intent() -> Intent:
        from ...powers import VulnerablePower
        return Intent(MoveType.DEBUFF, buffs=[(VulnerablePower, _VULNERABLE_AMT)])

    def _claw(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CLAW_DMG, _CLAW_HITS)

    def _rip(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _RIP_DMG, 1)

    def _roar(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _VULNERABLE_AMT)


MAWLER_NORMAL = Encounter(
    id="mawler_normal",
    monster_classes=[Mawler],
)
