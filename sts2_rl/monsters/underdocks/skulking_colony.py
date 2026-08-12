from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_ZOOM_DMG = 14              # SkulkingColony.cs:43 base
_ZOOM_DMG_ASC = 16          # DeadlyEnemies
_INERTIA_DMG = 9            # SkulkingColony.cs:41 base
_INERTIA_DMG_ASC = 11       # DeadlyEnemies
_INERTIA_STR = 2            # SkulkingColony.cs:49 base
_INERTIA_STR_ASC = 4        # DeadlyEnemies
_PIERCING_STABS_DMG = 7     # SkulkingColony.cs:45 base
_PIERCING_STABS_DMG_ASC = 8 # DeadlyEnemies
_PIERCING_STABS_HITS = 2
_HARDENED_SHELL = 20


class SkulkingColony(MachineMonster):
    """Elite. Hardened Shell 20 caps its HP loss per side-turn; loops
    ZOOM (14) → ZOOM (14) → INERTIA (9 + self 2 Str) → PIERCING_STABS (7×2)."""
    name = "Skulking Colony"

    min_hp = 75              # SkulkingColony.cs:37 base
    max_hp = 75
    min_hp_asc = 80          # SkulkingColony.cs:37 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 80

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import HardenedShellPower
        PowerCmd.apply(hooks, self, HardenedShellPower, _HARDENED_SHELL)

    def _zoom_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ZOOM_DMG_ASC, _ZOOM_DMG)

    def _inertia_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _INERTIA_DMG_ASC, _INERTIA_DMG)

    def _inertia_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _INERTIA_STR_ASC, _INERTIA_STR)

    def _piercing_stabs_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PIERCING_STABS_DMG_ASC, _PIERCING_STABS_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        zoom = MoveState(
            "ZOOM_MOVE", self._zoom, Intent(MoveType.ATTACK, damage=self._zoom_dmg())
        )
        zoom2 = MoveState(
            "ZOOM_MOVE_2", self._zoom, Intent(MoveType.ATTACK, damage=self._zoom_dmg())
        )
        inertia = MoveState(
            "INERTIA_MOVE", self._inertia,
            Intent(MoveType.ATTACK, damage=self._inertia_dmg(), also=(MoveType.BUFF,)),
        )
        piercing_stabs = MoveState(
            "PIERCING_STABS_MOVE", self._piercing_stabs,
            Intent(MoveType.ATTACK, damage=self._piercing_stabs_dmg(),
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
        self._execute_attack(ctx, self._zoom_dmg(), 1)

    def _inertia(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._inertia_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._inertia_str())

    def _piercing_stabs(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._piercing_stabs_dmg(), _PIERCING_STABS_HITS)


SKULKING_COLONY_ELITE = Encounter(
    id="skulking_colony_elite",
    monster_classes=[SkulkingColony],
)
