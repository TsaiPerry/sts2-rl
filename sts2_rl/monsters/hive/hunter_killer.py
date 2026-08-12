"""Hunter Killer (Hive). Sources: HunterKiller.cs, HunterKillerNormal.cs."""
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

_BITE_DMG = 17          # HunterKiller.cs:27 base
_BITE_DMG_ASC = 19      # DeadlyEnemies (asc 9+)
_PUNCTURE_DMG = 7       # HunterKiller.cs:29 base
_PUNCTURE_DMG_ASC = 8   # DeadlyEnemies (asc 9+)
_PUNCTURE_HITS = 3
_GOOP_TENDER = 1


class HunterKiller(MachineMonster):
    """Opens with TENDERIZING_GOOP (Tender 1: each card played costs the
    player 1 Strength and 1 Dexterity until end of turn), then rolls BITE (17,
    never twice in a row) or PUNCTURE (7x3, at most twice in a row) — both
    weight 1."""
    name = "Hunter Killer"

    min_hp = 121
    max_hp = 121
    min_hp_asc = 126     # HunterKiller.cs:23 ToughEnemies (asc 8+)
    max_hp_asc = 126     # HunterKiller.cs:25 `MaxInitialHp => MinInitialHp`

    def _bite_dmg(self) -> int:
        """HunterKiller.cs:27 `BiteDamage` -- read at both the telegraphed
        Intent (:39) and the executed attack (:60)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BITE_DMG_ASC, _BITE_DMG)

    def _puncture_dmg(self) -> int:
        """HunterKiller.cs:29 `PunctureDamage` -- read at both the telegraphed
        Intent (:40) and the executed attack (:68)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PUNCTURE_DMG_ASC, _PUNCTURE_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        goop = MoveState("TENDERIZING_GOOP_MOVE", self._goop, Intent(MoveType.DEBUFF))
        bite = MoveState(
            "BITE_MOVE", self._bite,
            lambda: Intent(MoveType.ATTACK, damage=self._bite_dmg()),
        )
        puncture = MoveState(
            "PUNCTURE_MOVE", self._puncture,
            lambda: Intent(MoveType.ATTACK, damage=self._puncture_dmg(),
                            hits=_PUNCTURE_HITS),
        )
        rand = RandomBranchState("RAND")
        rand.add_branch(bite, 1.0, MoveRepeatType.CANNOT_REPEAT)
        # HunterKiller.cs:43 AddBranch(state, 2) is the (state, int maxRepeats)
        # overload — a repeat limit, not a weight.
        rand.add_branch(
            puncture, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
        )
        goop.follow_up = rand
        bite.follow_up = rand
        puncture.follow_up = rand
        return MonsterMoveStateMachine([goop, bite, puncture, rand], goop)

    def _goop(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import TenderPower
        PowerCmd.apply(ctx.hooks, ctx.player, TenderPower, _GOOP_TENDER, applier=self)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._bite_dmg(), 1)

    def _puncture(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._puncture_dmg(), _PUNCTURE_HITS)


HUNTER_KILLER_NORMAL = Encounter(
    id="hunter_killer_normal",
    monster_classes=[HunterKiller],
)
