"""Tunneler (Hive). Sources: Tunneler.cs, TunnelerWeak.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx

_BITE_DMG = 13
_BURROW_BLOCK = 32
_BELOW_DMG = 23


class Tunneler(MachineMonster):
    """BITE (13) → BURROW (32 block that persists between turns) → BELOW (23)
    forever. Breaking its block while burrowed digs it out: it loses a turn
    (DIZZY) and starts over at BITE (see BurrowedPower)."""

    min_hp = 87
    max_hp = 87

    def build_machine(self) -> MonsterMoveStateMachine:
        bite = MoveState(
            "BITE_MOVE", self._bite, Intent(MoveType.ATTACK, damage=_BITE_DMG)
        )
        burrow = MoveState(
            "BURROW_MOVE", self._burrow,
            Intent(MoveType.BUFF, also=(MoveType.DEFEND,)),
        )
        below = MoveState(
            "BELOW_MOVE", self._below, Intent(MoveType.ATTACK, damage=_BELOW_DMG)
        )
        dizzy = MoveState("DIZZY_MOVE", self._dizzy, Intent(MoveType.STUN))
        bite.follow_up = burrow
        burrow.follow_up = below
        below.follow_up = below
        dizzy.follow_up = bite
        return MonsterMoveStateMachine([bite, burrow, below, dizzy], bite)

    def get_stunned(self) -> None:
        """Called by BurrowedPower when the burrow block is broken."""
        dizzy = self.machine.states["DIZZY_MOVE"]
        self.machine.force_current_state(dizzy)
        self._current_move = dizzy

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _burrow(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import BurrowedPower
        PowerCmd.apply(ctx.hooks, self, BurrowedPower, 1)
        BlockCmd.apply(ctx.hooks, self, _BURROW_BLOCK)

    def _below(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BELOW_DMG, 1)

    def _dizzy(self, ctx: CombatCtx) -> None:
        pass


TUNNELER_WEAK = Encounter(
    id="tunneler_weak",
    monster_classes=[Tunneler],
)
