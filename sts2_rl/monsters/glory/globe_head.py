from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_THUNDER_DMG = 6
_THUNDER_HITS = 3
_SLAP_DMG = 13
_SLAP_FRAIL = 2
_BURST_DMG = 16
_BURST_STR = 2
_GALVANIC = 6


class GlobeHead(MachineMonster):
    """Shocking Slap (13 + Frail 2) → Thunder Strike (6×3) → Galvanic Burst (16
    + gain 2 Strength) → loop. Starts with Galvanic 6, which afflicts the
    player's Power cards with Galvanized (they zap the player for 6 when played).

    Source: GlobeHead.cs (non-ascension values)."""

    min_hp = 148
    max_hp = 148

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import GalvanicPower
        PowerCmd.apply(hooks, self, GalvanicPower, _GALVANIC)

    def build_machine(self) -> MonsterMoveStateMachine:
        thunder = MoveState(
            "THUNDER_STRIKE", self._thunder,
            Intent(MoveType.ATTACK, damage=_THUNDER_DMG, hits=_THUNDER_HITS),
        )
        slap = MoveState(
            "SHOCKING_SLAP", self._slap,
            Intent(MoveType.ATTACK, damage=_SLAP_DMG, also=(MoveType.DEBUFF,)),
        )
        burst = MoveState(
            "GALVANIC_BURST", self._burst,
            Intent(MoveType.ATTACK, damage=_BURST_DMG, also=(MoveType.BUFF,)),
        )
        slap.follow_up = thunder
        thunder.follow_up = burst
        burst.follow_up = slap
        return MonsterMoveStateMachine([slap, thunder, burst], slap)

    def _thunder(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _THUNDER_DMG, _THUNDER_HITS)

    def _slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SLAP_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _SLAP_FRAIL)

    def _burst(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BURST_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _BURST_STR)


GLOBE_HEAD_NORMAL = Encounter(
    id="globe_head_normal",
    monster_classes=[GlobeHead],
)
