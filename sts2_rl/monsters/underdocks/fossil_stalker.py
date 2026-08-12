from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
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

_TACKLE_DMG = 9         # FossilStalker.cs:33 base
_TACKLE_DMG_ASC = 11    # DeadlyEnemies (asc 9+)
_TACKLE_FRAIL = 1
_LATCH_DMG = 12         # FossilStalker.cs:35 base
_LATCH_DMG_ASC = 14     # DeadlyEnemies (asc 9+)
_LASH_DMG = 3           # FossilStalker.cs:37 base
_LASH_DMG_ASC = 4       # DeadlyEnemies (asc 9+)
_LASH_HITS = 2
_SUCK_STR = 3


class FossilStalker(MachineMonster):
    """Starts with LATCH, then rolls each turn among TACKLE / LATCH / LASH with
    equal weight, none more than twice in a row. Suck: +3 Strength per hit
    that deals unblocked damage."""
    name = "Fossil Stalker"

    min_hp = 51
    max_hp = 53
    min_hp_asc = 54      # FossilStalker.cs:29 ToughEnemies (asc 8+)
    max_hp_asc = 56      # FossilStalker.cs:31

    def _tackle_dmg(self) -> int:
        """FossilStalker.cs:33 `TackleDamage` -- read at both the telegraphed
        Intent (:54) and the executed attack (:70)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _TACKLE_DMG_ASC, _TACKLE_DMG)

    def _latch_dmg(self) -> int:
        """FossilStalker.cs:35 `LatchDamage` -- read at both the telegraphed
        Intent (:55) and the executed attack (:79)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _LATCH_DMG_ASC, _LATCH_DMG)

    def _lash_dmg(self) -> int:
        """FossilStalker.cs:37 `LashDamage` -- read at both the telegraphed
        Intent (:56) and the executed attack (:87)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _LASH_DMG_ASC, _LASH_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SuckPower
        PowerCmd.apply(hooks, self, SuckPower, _SUCK_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        tackle = MoveState(
            "TACKLE_MOVE", self._tackle,
            lambda: Intent(MoveType.ATTACK, damage=self._tackle_dmg(), also=(MoveType.DEBUFF,)),
        )
        latch = MoveState(
            "LATCH_MOVE", self._latch,
            lambda: Intent(MoveType.ATTACK, damage=self._latch_dmg()),
        )
        lash = MoveState(
            "LASH_MOVE", self._lash,
            lambda: Intent(MoveType.ATTACK, damage=self._lash_dmg(), hits=_LASH_HITS),
        )
        branch = RandomBranchState("RAND")
        for move in (latch, tackle, lash):
            move.follow_up = branch
            branch.add_branch(
                move, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
            )
        return MonsterMoveStateMachine([branch, tackle, latch, lash], latch)

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._tackle_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _TACKLE_FRAIL)

    def _latch(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._latch_dmg(), 1)

    def _lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._lash_dmg(), _LASH_HITS)


FOSSIL_STALKER_NORMAL = Encounter(
    id="fossil_stalker_normal",
    monster_classes=[FossilStalker],
)
