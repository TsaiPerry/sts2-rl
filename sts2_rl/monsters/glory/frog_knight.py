from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_FOR_THE_QUEEN_STR = 5
_STRIKE_DOWN_DMG = 21
_TONGUE_LASH_DMG = 13
_TONGUE_LASH_FRAIL = 2
_BEETLE_CHARGE_DMG = 35
_PLATING = 15


class FrogKnight(MachineMonster):
    """Tongue Lash (13 + Frail 2) → Strike Down Evil (21) → For the Queen (+5
    Strength) → loop. Once below half HP it makes one Beetle Charge (35) before
    resuming. Starts with Plating 15.

    Source: FrogKnight.cs (non-ascension values)."""

    min_hp = 191
    max_hp = 191

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._has_beetle_charged = False
        from ...cmds import PowerCmd
        from ...powers import PlatingPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)

    def build_machine(self) -> MonsterMoveStateMachine:
        for_the_queen = MoveState(
            "FOR_THE_QUEEN", self._for_the_queen, Intent(MoveType.BUFF)
        )
        strike_down = MoveState(
            "STRIKE_DOWN_EVIL", self._strike_down,
            Intent(MoveType.ATTACK, damage=_STRIKE_DOWN_DMG),
        )
        tongue_lash = MoveState(
            "TONGUE_LASH", self._tongue_lash,
            Intent(MoveType.ATTACK, damage=_TONGUE_LASH_DMG, also=(MoveType.DEBUFF,)),
        )
        beetle_charge = MoveState(
            "BEETLE_CHARGE", self._beetle_charge,
            Intent(MoveType.ATTACK, damage=_BEETLE_CHARGE_DMG),
        )
        branch = ConditionalBranchState("HALF_HEALTH")
        branch.add_state(
            tongue_lash,
            lambda: self._has_beetle_charged or self.hp >= self.max_hp // 2,
        )
        branch.add_state(
            beetle_charge,
            lambda: not self._has_beetle_charged and self.hp < self.max_hp // 2,
        )
        for_the_queen.follow_up = branch
        strike_down.follow_up = for_the_queen
        tongue_lash.follow_up = strike_down
        beetle_charge.follow_up = tongue_lash
        return MonsterMoveStateMachine(
            [branch, for_the_queen, strike_down, tongue_lash, beetle_charge],
            tongue_lash,
        )

    def _for_the_queen(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _FOR_THE_QUEEN_STR)

    def _strike_down(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STRIKE_DOWN_DMG, 1)

    def _tongue_lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _TONGUE_LASH_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _TONGUE_LASH_FRAIL)

    def _beetle_charge(self, ctx: CombatCtx) -> None:
        self._has_beetle_charged = True
        self._execute_attack(ctx, _BEETLE_CHARGE_DMG, 1)


FROG_KNIGHT_NORMAL = Encounter(
    id="frog_knight_normal",
    monster_classes=[FrogKnight],
)
