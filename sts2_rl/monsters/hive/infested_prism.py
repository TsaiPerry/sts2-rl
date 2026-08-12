"""Infested Prism (Hive elite). Sources: InfestedPrism.cs,
InfestedPrismsElite.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JAB_DMG = 15               # InfestedPrism.cs:38 base
_JAB_DMG_ASC = 17           # DeadlyEnemies (asc 9+)
_RADIATE_DMG = 11           # InfestedPrism.cs:46 base
_RADIATE_DMG_ASC = 13       # DeadlyEnemies (asc 9+)
_RADIATE_BLOCK = 11         # InfestedPrism.cs:48 base -- gated on DeadlyEnemies (not ToughEnemies)
_RADIATE_BLOCK_ASC = 13     # DeadlyEnemies (asc 9+)
_WHIRLWIND_DMG = 5          # InfestedPrism.cs:50 base
_WHIRLWIND_DMG_ASC = 6      # DeadlyEnemies (asc 9+)
_WHIRLWIND_HITS = 3
_PULSATE_DMG = 8            # InfestedPrism.cs:42 base
_PULSATE_DMG_ASC = 10       # DeadlyEnemies (asc 9+)
_PULSATE_BLOCK = 20         # InfestedPrism.cs:44 base -- gated on ToughEnemies
_PULSATE_BLOCK_ASC = 22     # ToughEnemies (asc 8+)
_VITAL_SPARK = 2            # InfestedPrism.cs:40 base
_VITAL_SPARK_ASC = 3        # DeadlyEnemies (asc 9+)


class InfestedPrism(MachineMonster):
    """Spawns with Vital Spark 2: your Skills are Tainted — playing one makes
    you take +2 attack damage that turn (stacks). Cycle: JAB (15) → RADIATE
    (11 + 11 block) → WHIRLWIND (5x3) → PULSATE (8 + 20 block + Vital Spark
    +2)."""
    name = "Infested Prism"

    min_hp = 161
    max_hp = 161
    min_hp_asc = 171     # InfestedPrism.cs:34 ToughEnemies (asc 8+)
    max_hp_asc = 171     # InfestedPrism.cs:36 `MaxInitialHp => MinInitialHp`

    def _vital_spark(self) -> int:
        """InfestedPrism.cs:40 `VitalSparkAmount` -- read at both the initial
        AfterAddedToRoom apply (:59) and the PULSATE apply (:114)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _VITAL_SPARK_ASC, _VITAL_SPARK)

    def _jab_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _JAB_DMG_ASC, _JAB_DMG)

    def _radiate_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RADIATE_DMG_ASC, _RADIATE_DMG)

    def _radiate_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RADIATE_BLOCK_ASC, _RADIATE_BLOCK)

    def _whirlwind_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _WHIRLWIND_DMG_ASC, _WHIRLWIND_DMG)

    def _pulsate_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PULSATE_DMG_ASC, _PULSATE_DMG)

    def _pulsate_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _PULSATE_BLOCK_ASC, _PULSATE_BLOCK)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import VitalSparkPower
        PowerCmd.apply(hooks, self, VitalSparkPower, self._vital_spark())

    def build_machine(self) -> MonsterMoveStateMachine:
        jab = MoveState(
            "JAB_MOVE", self._jab,
            lambda: Intent(MoveType.ATTACK, damage=self._jab_dmg()),
        )
        radiate = MoveState(
            "RADIATE_MOVE", self._radiate,
            lambda: Intent(MoveType.ATTACK, damage=self._radiate_dmg(),
                            also=(MoveType.DEFEND,)),
        )
        whirlwind = MoveState(
            "WHIRLWIND_MOVE", self._whirlwind,
            lambda: Intent(MoveType.ATTACK, damage=self._whirlwind_dmg(),
                            hits=_WHIRLWIND_HITS),
        )
        pulsate = MoveState(
            "PULSATE_MOVE", self._pulsate,
            lambda: Intent(MoveType.ATTACK, damage=self._pulsate_dmg(),
                            also=(MoveType.BUFF, MoveType.DEFEND)),
        )
        jab.follow_up = radiate
        radiate.follow_up = whirlwind
        whirlwind.follow_up = pulsate
        pulsate.follow_up = jab
        return MonsterMoveStateMachine([jab, radiate, whirlwind, pulsate], jab)

    def _jab(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._jab_dmg(), 1)

    def _radiate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._radiate_dmg(), 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, self._radiate_block())

    def _whirlwind(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._whirlwind_dmg(), _WHIRLWIND_HITS)

    def _pulsate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._pulsate_dmg(), 1)
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import VitalSparkPower
        BlockCmd.apply(ctx.hooks, self, self._pulsate_block())
        PowerCmd.apply(ctx.hooks, self, VitalSparkPower, self._vital_spark())


INFESTED_PRISMS_ELITE = Encounter(
    id="infested_prisms_elite",
    monster_classes=[InfestedPrism],
)
