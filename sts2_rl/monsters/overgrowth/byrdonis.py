from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PECK_DMG = 3
_PECK_HITS = 3
_SWOOP_DMG = 17


class Byrdonis(MachineMonster):
    """SWOOP → PECK → SWOOP → ... (a fixed two-move loop, as in the source)."""

    min_hp = 81
    max_hp = 84

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import TerritorialPower
        PowerCmd.apply(hooks, self, TerritorialPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        swoop = MoveState(
            "SWOOP_MOVE", self._swoop, Intent(MoveType.ATTACK, damage=_SWOOP_DMG)
        )
        peck = MoveState(
            "PECK_MOVE", self._peck,
            Intent(MoveType.ATTACK, damage=_PECK_DMG, hits=_PECK_HITS),
        )
        swoop.follow_up = peck
        peck.follow_up = swoop
        return MonsterMoveStateMachine([swoop, peck], swoop)

    def _swoop(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SWOOP_DMG, 1)

    def _peck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PECK_DMG, _PECK_HITS)


BYRDONIS_ELITE = Encounter(
    id="byrdonis_elite",
    monster_classes=[Byrdonis],
)
