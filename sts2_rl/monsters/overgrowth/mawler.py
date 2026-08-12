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

_CLAW_DMG = 4           # Mawler.cs:27 base
_CLAW_DMG_ASC = 5       # DeadlyEnemies
_CLAW_HITS = 2
_RIP_DMG = 14           # Mawler.cs:25 base
_RIP_DMG_ASC = 16       # DeadlyEnemies
_VULNERABLE_AMT = 3


class Mawler(MachineMonster):
    """Starts with CLAW, then picks randomly each turn among RIP_AND_TEAR
    (no consecutive repeats), ROAR (usable once per combat), and CLAW
    (no consecutive repeats), all with equal weight."""
    min_hp = 72
    max_hp = 72
    min_hp_asc = 76   # Mawler.cs:21 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 76

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _claw_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CLAW_DMG_ASC, _CLAW_DMG)

    def _rip_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RIP_DMG_ASC, _RIP_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        claw = MoveState(
            "CLAW", self._claw,
            lambda: Intent(MoveType.ATTACK, damage=self._claw_dmg(), hits=_CLAW_HITS),
        )
        rip = MoveState(
            "RIP_AND_TEAR", self._rip, lambda: Intent(MoveType.ATTACK, damage=self._rip_dmg())
        )
        roar = MoveState("ROAR", self._roar, self._roar_intent)
        branch = RandomBranchState("BRANCH")
        branch.add_branch(rip, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(roar, repeat_type=MoveRepeatType.USE_ONLY_ONCE)
        branch.add_branch(claw, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        claw.follow_up = branch
        rip.follow_up = branch
        roar.follow_up = branch
        return MonsterMoveStateMachine([claw, rip, roar, branch], claw)

    @staticmethod
    def _roar_intent() -> Intent:
        from ...powers import VulnerablePower
        return Intent(MoveType.DEBUFF, buffs=[(VulnerablePower, _VULNERABLE_AMT)])

    def _claw(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._claw_dmg(), _CLAW_HITS)

    def _rip(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._rip_dmg(), 1)

    def _roar(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _VULNERABLE_AMT)


MAWLER_NORMAL = Encounter(
    id="mawler_normal",
    monster_classes=[Mawler],
)
