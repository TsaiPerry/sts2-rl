from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_ZOOM_DMG = 14
_INERTIA_DMG = 9
_INERTIA_STR = 2
_PIERCING_STABS_DMG = 7
_PIERCING_STABS_HITS = 2
_HARDENED_SHELL = 20


class SkulkingColony(MachineMonster):
    """Elite. Hardened Shell 20 caps its HP loss per side-turn; loops
    ZOOM (14) → ZOOM (14) → INERTIA (9 + self 2 Str) → PIERCING_STABS (7×2)."""

    min_hp = 75
    max_hp = 75

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import HardenedShellPower
        PowerCmd.apply(hooks, self, HardenedShellPower, _HARDENED_SHELL)

    def build_machine(self) -> MonsterMoveStateMachine:
        zoom = MoveState(
            "ZOOM_MOVE", self._zoom, Intent(MoveType.ATTACK, damage=_ZOOM_DMG)
        )
        zoom2 = MoveState(
            "ZOOM_MOVE_2", self._zoom, Intent(MoveType.ATTACK, damage=_ZOOM_DMG)
        )
        inertia = MoveState(
            "INERTIA_MOVE", self._inertia,
            Intent(MoveType.ATTACK, damage=_INERTIA_DMG, also=(MoveType.BUFF,)),
        )
        piercing_stabs = MoveState(
            "PIERCING_STABS_MOVE", self._piercing_stabs,
            Intent(MoveType.ATTACK, damage=_PIERCING_STABS_DMG,
                   hits=_PIERCING_STABS_HITS),
        )
        zoom.follow_up = zoom2
        zoom2.follow_up = inertia
        inertia.follow_up = piercing_stabs
        piercing_stabs.follow_up = zoom
        return MonsterMoveStateMachine(
            [zoom, zoom2, inertia, piercing_stabs], zoom
        )

    def _zoom(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ZOOM_DMG, 1)

    def _inertia(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _INERTIA_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _INERTIA_STR)

    def _piercing_stabs(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PIERCING_STABS_DMG, _PIERCING_STABS_HITS)


SKULKING_COLONY_ELITE = Encounter(
    id="skulking_colony_elite",
    monster_classes=[SkulkingColony],
)
