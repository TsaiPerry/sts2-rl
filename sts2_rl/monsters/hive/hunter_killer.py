"""Hunter Killer (Hive). Sources: HunterKiller.cs, HunterKillerNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx

_BITE_DMG = 17
_PUNCTURE_DMG = 7
_PUNCTURE_HITS = 3
_GOOP_TENDER = 1


class HunterKiller(MachineMonster):
    """Opens with TENDERIZING_GOOP (Tender 1: each card played costs the
    player 1 Strength and 1 Dexterity until end of turn), then rolls BITE (17,
    never twice in a row, weight 1) or PUNCTURE (7x3, weight 2)."""
    name = "Hunter Killer"

    min_hp = 121
    max_hp = 121

    def build_machine(self) -> MonsterMoveStateMachine:
        goop = MoveState("TENDERIZING_GOOP_MOVE", self._goop, Intent(MoveType.DEBUFF))
        bite = MoveState(
            "BITE_MOVE", self._bite, Intent(MoveType.ATTACK, damage=_BITE_DMG)
        )
        puncture = MoveState(
            "PUNCTURE_MOVE", self._puncture,
            Intent(MoveType.ATTACK, damage=_PUNCTURE_DMG, hits=_PUNCTURE_HITS),
        )
        rand = RandomBranchState("RAND")
        rand.add_branch(bite, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(puncture, 2.0)
        goop.follow_up = rand
        bite.follow_up = rand
        puncture.follow_up = rand
        return MonsterMoveStateMachine([goop, bite, puncture, rand], goop)

    def _goop(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import TenderPower
        PowerCmd.apply(ctx.hooks, ctx.player, TenderPower, _GOOP_TENDER, applier=self)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _puncture(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PUNCTURE_DMG, _PUNCTURE_HITS)


HUNTER_KILLER_NORMAL = Encounter(
    id="hunter_killer_normal",
    monster_classes=[HunterKiller],
)
