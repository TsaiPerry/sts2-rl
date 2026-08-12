from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JET_DMG = 10           # SewerClam.cs:25 base
_JET_DMG_ASC = 11       # DeadlyEnemies
_PRESSURIZE_STR = 4
_PLATING = 8            # SewerClam.cs:32 base
_PLATING_ASC = 9        # ToughEnemies


class SewerClam(MachineMonster):
    """Starts with Plating 8 (and its block); alternates JET (10) and
    PRESSURIZE (+4 Strength), starting with JET."""
    name = "Sewer Clam"

    min_hp = 56              # SewerClam.cs:21 base
    max_hp = 56
    min_hp_asc = 58          # SewerClam.cs:21 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 58

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PlatingPower
        plating = asc_value(hooks, AscensionLevel.TOUGH_ENEMIES, _PLATING_ASC, _PLATING)
        PowerCmd.apply(hooks, self, PlatingPower, plating)

    def _jet_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _JET_DMG_ASC, _JET_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        pressurize = MoveState(
            "PRESSURIZE_MOVE", self._pressurize, Intent(MoveType.BUFF)
        )
        jet = MoveState(
            "JET_MOVE", self._jet, Intent(MoveType.ATTACK, damage=self._jet_dmg())
        )
        pressurize.follow_up = jet
        jet.follow_up = pressurize
        return MonsterMoveStateMachine([pressurize, jet], jet)

    def _pressurize(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _PRESSURIZE_STR)

    def _jet(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._jet_dmg(), 1)


SEWER_CLAM_NORMAL = Encounter(
    id="sewer_clam_normal",
    monster_classes=[SewerClam],
)
