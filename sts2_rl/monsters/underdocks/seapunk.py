from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState
from .cultists import CalcifiedCultist

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SEA_KICK_DMG = 11      # Seapunk.cs:32 base
_SEA_KICK_DMG_ASC = 13  # DeadlyEnemies
_SPINNING_KICK_DMG = 2
_SPINNING_KICK_HITS = 4
_BUBBLE_BLOCK = 7       # Seapunk.cs:38 base
_BUBBLE_BLOCK_ASC = 8   # ToughEnemies
_BUBBLE_STR = 1         # Seapunk.cs:40 base
_BUBBLE_STR_ASC = 2     # DeadlyEnemies


class Seapunk(MachineMonster):
    """SEA_KICK (11) → SPINNING_KICK (2×4) → BUBBLE_BURP (7 block + 1 Str)
    → loop."""

    min_hp = 44              # Seapunk.cs:28 base
    max_hp = 46               # Seapunk.cs:30 base
    min_hp_asc = 47           # Seapunk.cs:28 -- ToughEnemies
    max_hp_asc = 49           # Seapunk.cs:30 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _sea_kick_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SEA_KICK_DMG_ASC, _SEA_KICK_DMG)

    def _bubble_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _BUBBLE_BLOCK_ASC, _BUBBLE_BLOCK)

    def _bubble_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BUBBLE_STR_ASC, _BUBBLE_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        sea_kick = MoveState(
            "SEA_KICK_MOVE", self._sea_kick,
            Intent(MoveType.ATTACK, damage=self._sea_kick_dmg()),
        )
        spinning_kick = MoveState(
            "SPINNING_KICK_MOVE", self._spinning_kick,
            Intent(MoveType.ATTACK, damage=_SPINNING_KICK_DMG,
                   hits=_SPINNING_KICK_HITS),
        )
        bubble_burp = MoveState(
            "BUBBLE_BURP_MOVE", self._bubble_burp,
            Intent(MoveType.BUFF, also=(MoveType.DEFEND,)),
        )
        sea_kick.follow_up = spinning_kick
        spinning_kick.follow_up = bubble_burp
        bubble_burp.follow_up = sea_kick
        return MonsterMoveStateMachine(
            [sea_kick, spinning_kick, bubble_burp], sea_kick
        )

    def _sea_kick(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._sea_kick_dmg(), 1)

    def _spinning_kick(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SPINNING_KICK_DMG, _SPINNING_KICK_HITS)

    def _bubble_burp(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        BlockCmd.apply(ctx.hooks, self, self._bubble_block())
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._bubble_str())


# The normal fight pairs the Seapunk with a Calcified Cultist (SeapunkNormal
# spawns the cultist first); the weak fight is the Seapunk alone.
SEAPUNK_NORMAL = Encounter(
    id="seapunk_normal",
    monster_classes=[CalcifiedCultist, Seapunk],
)
SEAPUNK_WEAK = Encounter(
    id="seapunk_weak",
    monster_classes=[Seapunk],
)
