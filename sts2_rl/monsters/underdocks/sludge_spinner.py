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

_OIL_SPRAY_DMG = 8      # SludgeSpinner.cs:30 base
_OIL_SPRAY_DMG_ASC = 9  # DeadlyEnemies
_OIL_SPRAY_WEAK = 1
_SLAM_DMG = 11          # SludgeSpinner.cs:32 base
_SLAM_DMG_ASC = 12      # DeadlyEnemies
_RAGE_DMG = 6           # SludgeSpinner.cs:34 base
_RAGE_DMG_ASC = 7       # DeadlyEnemies
_RAGE_STR = 3


class SludgeSpinner(MachineMonster):
    """Opens with OIL_SPRAY (8 + Weak 1); afterwards picks uniformly among
    OIL_SPRAY / SLAM (11) / RAGE (6 + self 3 Str) without repeating the same
    move twice in a row."""
    name = "Sludge Spinner"

    min_hp = 37              # SludgeSpinner.cs:26 base
    max_hp = 39                # SludgeSpinner.cs:28 base
    min_hp_asc = 41             # SludgeSpinner.cs:26 -- ToughEnemies
    max_hp_asc = 42             # SludgeSpinner.cs:28 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _oil_spray_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _OIL_SPRAY_DMG_ASC, _OIL_SPRAY_DMG)

    def _slam_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLAM_DMG_ASC, _SLAM_DMG)

    def _rage_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RAGE_DMG_ASC, _RAGE_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        oil_spray = MoveState(
            "OIL_SPRAY_MOVE", self._oil_spray,
            Intent(MoveType.ATTACK, damage=self._oil_spray_dmg(),
                   also=(MoveType.DEBUFF,)),
        )
        slam = MoveState(
            "SLAM_MOVE", self._slam, Intent(MoveType.ATTACK, damage=self._slam_dmg())
        )
        rage = MoveState(
            "RAGE_MOVE", self._rage,
            Intent(MoveType.ATTACK, damage=self._rage_dmg(), also=(MoveType.BUFF,)),
        )
        rand = RandomBranchState("RAND")
        oil_spray.follow_up = rand
        slam.follow_up = rand
        rage.follow_up = rand
        rand.add_branch(oil_spray, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(slam, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(rage, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        return MonsterMoveStateMachine([rand, oil_spray, slam, rage], oil_spray)

    def _oil_spray(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._oil_spray_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _OIL_SPRAY_WEAK)

    def _slam(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._slam_dmg(), 1)

    def _rage(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._rage_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _RAGE_STR)


SLUDGE_SPINNER_WEAK = Encounter(
    id="sludge_spinner_weak",
    monster_classes=[SludgeSpinner],
)
