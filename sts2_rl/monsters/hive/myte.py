"""Myte (Hive). Sources: Myte.cs, MytesNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_TOXIC_COUNT = 2
_BITE_DMG = 13
_SUCK_DMG = 4
_SUCK_STR = 2


class Myte(MachineMonster):
    """Cycle: TOXIC (2 Toxic cards into the hand) → BITE (13) → SUCK (4 +
    2 self Strength). The first Myte opens with TOXIC, the second with SUCK."""

    min_hp = 61
    max_hp = 67

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        slot: str = "first",
    ) -> None:
        self.slot = slot
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        toxic = MoveState("TOXIC_MOVE", self._toxic, Intent(MoveType.STATUS_CARD))
        bite = MoveState(
            "BITE_MOVE", self._bite, Intent(MoveType.ATTACK, damage=_BITE_DMG)
        )
        suck = MoveState(
            "SUCK_MOVE", self._suck,
            Intent(MoveType.ATTACK, damage=_SUCK_DMG, also=(MoveType.BUFF,)),
        )
        init = ConditionalBranchState("INIT_MOVE")
        init.add_state(toxic, lambda: self.slot == "first")
        init.add_state(suck, lambda: self.slot == "second")
        toxic.follow_up = bite
        bite.follow_up = suck
        suck.follow_up = toxic
        return MonsterMoveStateMachine([toxic, bite, suck, init], init)

    def _toxic(self, ctx: CombatCtx) -> None:
        from ...cards import ToxicCard
        from ...cmds import CardPileCmd
        for _ in range(_TOXIC_COUNT):
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, ToxicCard())

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _suck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SUCK_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _SUCK_STR)


@dataclass
class MytesEncounter(Encounter):
    """Two Mytes offset in the cycle (slots first / second)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [Myte(hooks, rng, slot="first"), Myte(hooks, rng, slot="second")]


MYTES_NORMAL = MytesEncounter(id="mytes_normal")
