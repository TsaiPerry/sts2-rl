"""Myte (Hive). Sources: Myte.cs, MytesNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
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
_BITE_DMG = 13       # Myte.cs:38 base
_BITE_DMG_ASC = 15   # DeadlyEnemies
_SUCK_DMG = 4        # Myte.cs:40 base
_SUCK_DMG_ASC = 6    # DeadlyEnemies
_SUCK_STR = 2        # Myte.cs:42 base
_SUCK_STR_ASC = 3    # DeadlyEnemies


class Myte(MachineMonster):
    """Cycle: TOXIC (2 Toxic cards into the hand) → BITE (13) → SUCK (4 +
    2 self Strength). The first Myte opens with TOXIC, the second with SUCK."""

    min_hp = 61
    max_hp = 67
    min_hp_asc = 64   # Myte.cs:34 -- ToughEnemies
    max_hp_asc = 69   # Myte.cs:36 -- ToughEnemies

    def _bite_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BITE_DMG_ASC, _BITE_DMG)

    def _suck_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SUCK_DMG_ASC, _SUCK_DMG)

    def _suck_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SUCK_STR_ASC, _SUCK_STR)

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        slot: str = "first",
    ) -> None:
        self.slot = slot
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        toxic = MoveState(
            "TOXIC_MOVE", self._toxic,
            Intent(MoveType.STATUS_CARD, status_count=_TOXIC_COUNT),
        )
        bite = MoveState(
            "BITE_MOVE", self._bite, lambda: Intent(MoveType.ATTACK, damage=self._bite_dmg())
        )
        suck = MoveState(
            "SUCK_MOVE", self._suck,
            lambda: Intent(MoveType.ATTACK, damage=self._suck_dmg(), also=(MoveType.BUFF,)),
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
        self._execute_attack(ctx, self._bite_dmg(), 1)

    def _suck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._suck_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._suck_str())


@dataclass
class MytesEncounter(Encounter):
    """Two Mytes offset in the cycle (slots first / second)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [Myte(hooks, rng, slot="first"), Myte(hooks, rng, slot="second")]


MYTES_NORMAL = MytesEncounter(
    id="mytes_normal",
    # MytesNormal.cs:14,32-39 — the row the two Mytes are seated in. The
    # sim also passes `slot=` to the Myte constructor, which drives its
    # opening-move choice; this is the `Creature.SlotName` the game reads.
    slots=("first", "second"),
    monster_slots=("first", "second"),
)
