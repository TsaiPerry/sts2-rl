"""Infested Prism (Hive elite). Sources: InfestedPrism.cs,
InfestedPrismsElite.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JAB_DMG = 15
_RADIATE_DMG = 11
_RADIATE_BLOCK = 11
_WHIRLWIND_DMG = 5
_WHIRLWIND_HITS = 3
_PULSATE_DMG = 8
_PULSATE_BLOCK = 20
_VITAL_SPARK = 2


class InfestedPrism(MachineMonster):
    """Spawns with Vital Spark 2: your Skills are Tainted — playing one makes
    you take +2 attack damage that turn (stacks). Cycle: JAB (15) → RADIATE
    (11 + 11 block) → WHIRLWIND (5x3) → PULSATE (8 + 20 block + Vital Spark
    +2)."""

    min_hp = 161
    max_hp = 161

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import VitalSparkPower
        PowerCmd.apply(hooks, self, VitalSparkPower, _VITAL_SPARK)

    def build_machine(self) -> MonsterMoveStateMachine:
        jab = MoveState(
            "JAB_MOVE", self._jab, Intent(MoveType.ATTACK, damage=_JAB_DMG)
        )
        radiate = MoveState(
            "RADIATE_MOVE", self._radiate,
            Intent(MoveType.ATTACK, damage=_RADIATE_DMG, also=(MoveType.DEFEND,)),
        )
        whirlwind = MoveState(
            "WHIRLWIND_MOVE", self._whirlwind,
            Intent(MoveType.ATTACK, damage=_WHIRLWIND_DMG, hits=_WHIRLWIND_HITS),
        )
        pulsate = MoveState(
            "PULSATE_MOVE", self._pulsate,
            Intent(MoveType.ATTACK, damage=_PULSATE_DMG,
                   also=(MoveType.BUFF, MoveType.DEFEND)),
        )
        jab.follow_up = radiate
        radiate.follow_up = whirlwind
        whirlwind.follow_up = pulsate
        pulsate.follow_up = jab
        return MonsterMoveStateMachine([jab, radiate, whirlwind, pulsate], jab)

    def _jab(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _JAB_DMG, 1)

    def _radiate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _RADIATE_DMG, 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _RADIATE_BLOCK)

    def _whirlwind(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WHIRLWIND_DMG, _WHIRLWIND_HITS)

    def _pulsate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PULSATE_DMG, 1)
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import VitalSparkPower
        BlockCmd.apply(ctx.hooks, self, _PULSATE_BLOCK)
        PowerCmd.apply(ctx.hooks, self, VitalSparkPower, _VITAL_SPARK)


INFESTED_PRISMS_ELITE = Encounter(
    id="infested_prisms_elite",
    monster_classes=[InfestedPrism],
)
