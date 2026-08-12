"""Exoskeleton (Hive). Sources: Exoskeleton.cs, ExoskeletonsWeak.cs,
ExoskeletonsNormal.cs."""
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
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SKITTER_DMG = 1
_SKITTER_HITS = 3        # Exoskeleton.cs:36 (SkitterRepeats) base
_SKITTER_HITS_ASC = 4    # DeadlyEnemies
_MANDIBLES_DMG = 8       # Exoskeleton.cs:38 base
_MANDIBLES_DMG_ASC = 9   # DeadlyEnemies
_ENRAGE_STR = 2
_HARD_TO_KILL = 9


class Exoskeleton(MachineMonster):
    """Spawns with Hard to Kill 9 (max 9 damage per hit). Opening move is
    fixed by slot (first: SKITTER 1x3, second: MANDIBLES 8, third: ENRAGE,
    fourth: random); MANDIBLES chains into ENRAGE, everything else rolls
    SKITTER/MANDIBLES without repeating."""

    min_hp = 24             # Exoskeleton.cs:30
    max_hp = 28              # Exoskeleton.cs:32
    min_hp_asc = 25          # Exoskeleton.cs:30 -- ToughEnemies
    max_hp_asc = 29          # Exoskeleton.cs:32 -- ToughEnemies

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

    def _skitter_hits(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SKITTER_HITS_ASC, _SKITTER_HITS)

    def _mandibles_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _MANDIBLES_DMG_ASC, _MANDIBLES_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        skitter = MoveState(
            "SKITTER_MOVE", self._skitter,
            Intent(MoveType.ATTACK, damage=_SKITTER_DMG, hits=self._skitter_hits()),
        )
        mandibles = MoveState(
            "MANDIBLES_MOVE", self._mandibles,
            Intent(MoveType.ATTACK, damage=self._mandibles_dmg()),
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
        self._execute_attack(ctx, _SKITTER_DMG, self._skitter_hits())

    def _mandibles(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._mandibles_dmg(), 1)

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

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [
            Exoskeleton(hooks, rng, slot=self._SLOTS[i]) for i in range(self.count)
        ]


EXOSKELETONS_WEAK = ExoskeletonsEncounter(id="exoskeletons_weak", count=3)
EXOSKELETONS_NORMAL = ExoskeletonsEncounter(id="exoskeletons_normal", count=4)
