"""Tunneler (Hive). Sources: Tunneler.cs, TunnelerWeak.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx

_BITE_DMG = 13          # Tunneler.cs:50 base
_BITE_DMG_ASC = 15      # DeadlyEnemies
_BURROW_BLOCK = 32      # Tunneler.cs:52 base -- ToughEnemies (note: gated by
                        # ToughEnemies, not DeadlyEnemies)
_BURROW_BLOCK_ASC = 37
_BELOW_DMG = 23         # Tunneler.cs:54 base
_BELOW_DMG_ASC = 26     # DeadlyEnemies


class Tunneler(MachineMonster):
    """BITE (13) → BURROW (32 block that persists between turns) → BELOW (23)
    forever. Breaking its block while burrowed digs it out: it loses a turn
    (DIZZY) and starts over at BITE (see BurrowedPower)."""

    min_hp = 87
    max_hp = 87
    min_hp_asc = 92   # Tunneler.cs:40 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 92

    def _bite_dmg(self) -> int:
        """Tunneler.cs:50 `BiteDamage` -- read at both the telegraphed
        Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BITE_DMG_ASC, _BITE_DMG)

    def _block_gain(self) -> int:
        """Tunneler.cs:52 `BlockGain` -- gated by ToughEnemies (asc 8+), not
        DeadlyEnemies, per the source call."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _BURROW_BLOCK_ASC, _BURROW_BLOCK)

    def _below_dmg(self) -> int:
        """Tunneler.cs:54 `BelowDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BELOW_DMG_ASC, _BELOW_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        bite = MoveState(
            "BITE_MOVE", self._bite, lambda: Intent(MoveType.ATTACK, damage=self._bite_dmg())
        )
        burrow = MoveState(
            "BURROW_MOVE", self._burrow,
            Intent(MoveType.BUFF, also=(MoveType.DEFEND,)),
        )
        below = MoveState(
            "BELOW_MOVE", self._below, lambda: Intent(MoveType.ATTACK, damage=self._below_dmg())
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
        self._execute_attack(ctx, self._bite_dmg(), 1)

    def _burrow(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import BurrowedPower
        PowerCmd.apply(ctx.hooks, self, BurrowedPower, 1)
        BlockCmd.apply(ctx.hooks, self, self._block_gain())

    def _below(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._below_dmg(), 1)

    def _dizzy(self, ctx: CombatCtx) -> None:
        pass


TUNNELER_WEAK = Encounter(
    id="tunneler_weak",
    monster_classes=[Tunneler],
)
