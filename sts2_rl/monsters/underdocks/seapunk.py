from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState
from .cultists import CalcifiedCultist

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SEA_KICK_DMG = 11
_SPINNING_KICK_DMG = 2
_SPINNING_KICK_HITS = 4
_BUBBLE_BLOCK = 7
_BUBBLE_STR = 1


class Seapunk(MachineMonster):
    """SEA_KICK (11) → SPINNING_KICK (2×4) → BUBBLE_BURP (7 block + 1 Str)
    → loop."""

    min_hp = 44
    max_hp = 46

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        sea_kick = MoveState(
            "SEA_KICK_MOVE", self._sea_kick,
            Intent(MoveType.ATTACK, damage=_SEA_KICK_DMG),
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
        self._execute_attack(ctx, _SEA_KICK_DMG, 1)

    def _spinning_kick(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SPINNING_KICK_DMG, _SPINNING_KICK_HITS)

    def _bubble_burp(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        BlockCmd.apply(ctx.hooks, self, _BUBBLE_BLOCK)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _BUBBLE_STR)


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
