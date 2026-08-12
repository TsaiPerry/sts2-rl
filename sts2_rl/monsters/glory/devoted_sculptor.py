from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_RITUAL_GAIN = 9         # DevotedSculptor.cs:21 -- not ascension-gated
_SAVAGE_DMG = 12         # DevotedSculptor.cs:29 base
_SAVAGE_DMG_ASC = 15     # DeadlyEnemies


class DevotedSculptor(MachineMonster):
    """Casts Forbidden Incantation (gain Ritual 9) once, then Savages (12) every
    turn while its Strength snowballs.

    Source: DevotedSculptor.cs."""
    name = "Devoted Sculptor"

    min_hp = 162            # DevotedSculptor.cs:23
    max_hp = 162
    min_hp_asc = 172         # DevotedSculptor.cs:23 -- ToughEnemies
    max_hp_asc = 172

    def _savage_dmg(self) -> int:
        """DevotedSculptor.cs:29 `SavageDamage` -- read at both the Intent
        and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SAVAGE_DMG_ASC, _SAVAGE_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        incantation = MoveState(
            "FORBIDDEN_INCANTATION_MOVE", self._incantation, Intent(MoveType.BUFF)
        )
        savage = MoveState(
            "SAVAGE_MOVE", self._savage,
            Intent(MoveType.ATTACK, damage=self._savage_dmg()),
        )
        incantation.follow_up = savage
        savage.follow_up = savage
        return MonsterMoveStateMachine([incantation, savage], incantation)

    def _incantation(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import RitualPower
        PowerCmd.apply(ctx.hooks, self, RitualPower, _RITUAL_GAIN, applier=self)

    def _savage(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._savage_dmg(), 1)


DEVOTED_SCULPTOR_WEAK = Encounter(
    id="devoted_sculptor_weak",
    monster_classes=[DevotedSculptor],
)
