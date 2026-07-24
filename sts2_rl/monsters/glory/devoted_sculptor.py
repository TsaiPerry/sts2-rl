from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_RITUAL_GAIN = 9
_SAVAGE_DMG = 12


class DevotedSculptor(MachineMonster):
    """Casts Forbidden Incantation (gain Ritual 9) once, then Savages (12) every
    turn while its Strength snowballs.

    Source: DevotedSculptor.cs (non-ascension values)."""
    name = "Devoted Sculptor"

    min_hp = 162
    max_hp = 162

    def build_machine(self) -> MonsterMoveStateMachine:
        incantation = MoveState(
            "FORBIDDEN_INCANTATION_MOVE", self._incantation, Intent(MoveType.BUFF)
        )
        savage = MoveState(
            "SAVAGE_MOVE", self._savage,
            Intent(MoveType.ATTACK, damage=_SAVAGE_DMG),
        )
        incantation.follow_up = savage
        savage.follow_up = savage
        return MonsterMoveStateMachine([incantation, savage], incantation)

    def _incantation(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import RitualPower
        PowerCmd.apply(ctx.hooks, self, RitualPower, _RITUAL_GAIN, applier=self)

    def _savage(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SAVAGE_DMG, 1)


DEVOTED_SCULPTOR_WEAK = Encounter(
    id="devoted_sculptor_weak",
    monster_classes=[DevotedSculptor],
)
