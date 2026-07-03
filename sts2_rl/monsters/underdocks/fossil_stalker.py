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

_TACKLE_DMG = 9
_TACKLE_FRAIL = 1
_LATCH_DMG = 12
_LASH_DMG = 3
_LASH_HITS = 2
_SUCK_STR = 3


class FossilStalker(MachineMonster):
    """Starts with LATCH, then rolls each turn among TACKLE / LATCH / LASH with
    equal weight, none more than twice in a row. Suck: +3 Strength per hit
    that deals unblocked damage."""

    min_hp = 51
    max_hp = 53

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SuckPower
        PowerCmd.apply(hooks, self, SuckPower, _SUCK_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        tackle = MoveState(
            "TACKLE_MOVE", self._tackle,
            Intent(MoveType.ATTACK, damage=_TACKLE_DMG, also=(MoveType.DEBUFF,)),
        )
        latch = MoveState(
            "LATCH_MOVE", self._latch, Intent(MoveType.ATTACK, damage=_LATCH_DMG)
        )
        lash = MoveState(
            "LASH_MOVE", self._lash,
            Intent(MoveType.ATTACK, damage=_LASH_DMG, hits=_LASH_HITS),
        )
        branch = RandomBranchState("RAND")
        for move in (latch, tackle, lash):
            move.follow_up = branch
            branch.add_branch(
                move, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
            )
        return MonsterMoveStateMachine([branch, tackle, latch, lash], latch)

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _TACKLE_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _TACKLE_FRAIL)

    def _latch(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LATCH_DMG, 1)

    def _lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LASH_DMG, _LASH_HITS)


FOSSIL_STALKER_NORMAL = Encounter(
    id="fossil_stalker_normal",
    monster_classes=[FossilStalker],
)
