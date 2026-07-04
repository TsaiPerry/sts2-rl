"""Slumbering Beetle (Hive). Sources: SlumberingBeetle.cs,
SlumberingBeetleNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_ROLLOUT_DMG = 16
_ROLLOUT_STR = 2
_PLATING = 15
_SLUMBER = 3


class SlumberingBeetle(MachineMonster):
    """Sleeps behind Plating 15 for 3 turns (Slumber 3; unblocked damage also
    counts down a turn and wakes it stunned at 0). Awake it ROLLs OUT every
    turn: 16 damage + 2 self Strength."""

    min_hp = 86
    max_hp = 86

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_awake = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PlatingPower, SlumberPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)
        PowerCmd.apply(hooks, self, SlumberPower, _SLUMBER)

    def build_machine(self) -> MonsterMoveStateMachine:
        snore = MoveState("SNORE_MOVE", self._snore, Intent(MoveType.SLEEP))
        rollout = MoveState(
            "ROLL_OUT_MOVE", self._rollout,
            Intent(MoveType.ATTACK, damage=_ROLLOUT_DMG, also=(MoveType.BUFF,)),
        )
        branch = ConditionalBranchState("SNORE_NEXT")
        branch.add_state(snore, lambda: "slumber" in self.powers)
        branch.add_state(rollout, lambda: "slumber" not in self.powers)
        snore.follow_up = branch
        rollout.follow_up = rollout
        return MonsterMoveStateMachine([snore, branch, rollout], snore)

    def wake_up(self, stunned: bool) -> None:
        """Called by SlumberPower. Waking removes the Plating; a damage wake
        costs the beetle its next turn (mirrors WakeUpMove +
        CreatureCmd.Stun(..., "ROLL_OUT_MOVE"))."""
        from ...cmds import CreatureCmd, PowerCmd
        self.is_awake = True
        PowerCmd.remove(self._hooks, self, "plating")
        rollout = self.machine.states["ROLL_OUT_MOVE"]
        self.machine.force_current_state(rollout)
        self._current_move = rollout
        if stunned:
            CreatureCmd.stun(self._hooks, self)

    def _snore(self, ctx: CombatCtx) -> None:
        pass

    def _rollout(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ROLLOUT_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ROLLOUT_STR)


@dataclass
class SlumberingBeetleEncounter(Encounter):
    """Bowlbug Rock + Bowlbug Silk guarding a Slumbering Beetle."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        from .bowlbugs import BowlbugRock, BowlbugSilk
        return [
            BowlbugRock(hooks, rng),
            BowlbugSilk(hooks, rng),
            SlumberingBeetle(hooks, rng),
        ]


SLUMBERING_BEETLE_NORMAL = SlumberingBeetleEncounter(id="slumbering_beetle_normal")
