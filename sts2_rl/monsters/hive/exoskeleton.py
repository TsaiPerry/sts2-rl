"""Exoskeleton (Hive). Sources: Exoskeleton.cs, ExoskeletonsWeak.cs,
ExoskeletonsNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SKITTER_DMG = 1
_SKITTER_HITS = 3
_MANDIBLES_DMG = 8
_ENRAGE_STR = 2
_HARD_TO_KILL = 9


class Exoskeleton(MachineMonster):
    """Spawns with Hard to Kill 9 (max 9 damage per hit). Opening move is
    fixed by slot (first: SKITTER 1x3, second: MANDIBLES 8, third: ENRAGE,
    fourth: random); MANDIBLES chains into ENRAGE, everything else rolls
    SKITTER/MANDIBLES without repeating."""

    min_hp = 24
    max_hp = 28

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        slot: str = "first",
    ) -> None:
        self.slot = slot
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import HardToKillPower
        PowerCmd.apply(hooks, self, HardToKillPower, _HARD_TO_KILL)

    def build_machine(self) -> MonsterMoveStateMachine:
        skitter = MoveState(
            "SKITTER_MOVE", self._skitter,
            Intent(MoveType.ATTACK, damage=_SKITTER_DMG, hits=_SKITTER_HITS),
        )
        mandibles = MoveState(
            "MANDIBLES_MOVE", self._mandibles,
            Intent(MoveType.ATTACK, damage=_MANDIBLES_DMG),
        )
        enrage = MoveState("ENRAGE_MOVE", self._enrage, Intent(MoveType.BUFF))
        rand = RandomBranchState("RAND")
        rand.add_branch(skitter, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(mandibles, 1.0, MoveRepeatType.CANNOT_REPEAT)
        init = ConditionalBranchState("INIT_MOVE")
        init.add_state(skitter, lambda: self.slot == "first")
        init.add_state(mandibles, lambda: self.slot == "second")
        init.add_state(enrage, lambda: self.slot == "third")
        init.add_state(rand, lambda: self.slot == "fourth")
        skitter.follow_up = rand
        mandibles.follow_up = enrage
        enrage.follow_up = rand
        return MonsterMoveStateMachine(
            [init, rand, skitter, mandibles, enrage], init
        )

    def _skitter(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SKITTER_DMG, _SKITTER_HITS)

    def _mandibles(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _MANDIBLES_DMG, 1)

    def _enrage(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STR)


@dataclass
class ExoskeletonsEncounter(Encounter):
    """N Exoskeletons in slots first..fourth."""

    monster_classes: list = field(default_factory=list)
    count: int = 3

    _SLOTS = ("first", "second", "third", "fourth")

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        return [
            Exoskeleton(hooks, rng, slot=self._SLOTS[i]) for i in range(self.count)
        ]


EXOSKELETONS_WEAK = ExoskeletonsEncounter(id="exoskeletons_weak", count=3)
EXOSKELETONS_NORMAL = ExoskeletonsEncounter(id="exoskeletons_normal", count=4)
