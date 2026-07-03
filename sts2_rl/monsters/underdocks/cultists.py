from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


class _Cultist(MachineMonster):
    """Shared cultist pattern: INCANTATION (gain Ritual) once, then DARK_STRIKE
    forever."""

    dark_strike_dmg: int
    incantation_amt: int

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        incantation = MoveState(
            "INCANTATION_MOVE", self._incantation, Intent(MoveType.BUFF)
        )
        dark_strike = MoveState(
            "DARK_STRIKE_MOVE", self._dark_strike,
            Intent(MoveType.ATTACK, damage=self.dark_strike_dmg),
        )
        incantation.follow_up = dark_strike
        dark_strike.follow_up = dark_strike
        return MonsterMoveStateMachine([incantation, dark_strike], incantation)

    def _incantation(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import RitualPower
        PowerCmd.apply(ctx.hooks, self, RitualPower, self.incantation_amt, applier=self)

    def _dark_strike(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self.dark_strike_dmg, 1)


class CalcifiedCultist(_Cultist):
    """Hits harder, smaller Ritual."""

    min_hp = 38
    max_hp = 41
    dark_strike_dmg = 9
    incantation_amt = 2


class DampCultist(_Cultist):
    """Hits for almost nothing, but Ritual 5 snowballs fast."""

    min_hp = 51
    max_hp = 53
    dark_strike_dmg = 1
    incantation_amt = 5


CULTISTS_NORMAL = Encounter(
    id="cultists_normal",
    monster_classes=[CalcifiedCultist, DampCultist],
)
