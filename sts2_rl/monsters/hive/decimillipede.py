"""Decimillipede (Hive elite). Sources: DecimillipedeSegment.cs,
DecimillipedeSegmentFront/Middle/Back.cs, DecimillipedeElite.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_WRITHE_DMG = 5
_WRITHE_HITS = 2
_BULK_DMG = 6
_BULK_STR = 2
_CONSTRICT_DMG = 8
_CONSTRICT_WEAK = 1
_REATTACH_HP = 25


class DecimillipedeSegment(MachineMonster):
    """One segment of the Decimillipede. Cycles WRITHE (5x2) / BULK (6 + 2
    Strength) / CONSTRICT (8 + Weak 1); segments start offset in the cycle.
    A killed segment withers instead of dying while another segment stands,
    then REATTACHes with 25 HP two of its turns later; the fight only ends
    when the last standing segment is killed (see ReattachPower)."""

    min_hp = 40
    max_hp = 46

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        starter_move_idx: int = 0,
    ) -> None:
        self.starter_move_idx = starter_move_idx
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ReattachPower
        PowerCmd.apply(hooks, self, ReattachPower, _REATTACH_HP)

    def build_machine(self) -> MonsterMoveStateMachine:
        writhe = MoveState(
            "WRITHE_MOVE", self._writhe,
            Intent(MoveType.ATTACK, damage=_WRITHE_DMG, hits=_WRITHE_HITS),
        )
        bulk = MoveState(
            "BULK_MOVE", self._bulk,
            Intent(MoveType.ATTACK, damage=_BULK_DMG, also=(MoveType.BUFF,)),
        )
        constrict = MoveState(
            "CONSTRICT_MOVE", self._constrict,
            Intent(MoveType.ATTACK, damage=_CONSTRICT_DMG, also=(MoveType.DEBUFF,)),
        )
        dead = MoveState("DEAD_MOVE", self._dead, Intent(MoveType.HIDDEN))
        reattach = MoveState(
            "REATTACH_MOVE", self._reattach, Intent(MoveType.HEAL),
            must_perform_once_before_transitioning=True,
        )
        constrict.follow_up = bulk
        bulk.follow_up = writhe
        writhe.follow_up = constrict
        rand = RandomBranchState("RAND")
        dead.follow_up = reattach
        reattach.follow_up = rand
        rand.add_branch(writhe, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(bulk, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(constrict, 1.0, MoveRepeatType.CANNOT_REPEAT)
        initial = (writhe, bulk, constrict)[self.starter_move_idx % 3]
        return MonsterMoveStateMachine(
            [writhe, bulk, constrict, dead, reattach, rand], initial
        )

    def enter_dead_state(self) -> None:
        """Called by ReattachPower when this segment's death is prevented."""
        dead = self.machine.states["DEAD_MOVE"]
        self.machine.force_current_state(dead)
        self._current_move = dead

    def _writhe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WRITHE_DMG, _WRITHE_HITS)

    def _bulk(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BULK_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _BULK_STR)

    def _constrict(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CONSTRICT_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _CONSTRICT_WEAK, applier=self)

    def _dead(self, ctx: CombatCtx) -> None:
        pass

    def _reattach(self, ctx: CombatCtx) -> None:
        reattach = self.powers.get("reattach")
        if reattach is not None:
            reattach.do_reattach()


class DecimillipedeSegmentFront(DecimillipedeSegment):
    """Visual-only subclass in the game; all logic is in DecimillipedeSegment."""


class DecimillipedeSegmentMiddle(DecimillipedeSegment):
    """Visual-only subclass in the game; all logic is in DecimillipedeSegment."""


class DecimillipedeSegmentBack(DecimillipedeSegment):
    """Visual-only subclass in the game; all logic is in DecimillipedeSegment."""


@dataclass
class DecimillipedeEncounter(Encounter):
    """Three segments on consecutive moves of the cycle, with distinct even
    max HP (mirrors DecimillipedeElite.GenerateMonsters and the HP-uniqueness
    pass in DecimillipedeSegment.AfterAddedToRoom)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        start = rng.randrange(3)
        segments: list[Monster] = [
            DecimillipedeSegmentFront(hooks, rng, starter_move_idx=start),
            DecimillipedeSegmentMiddle(hooks, rng, starter_move_idx=(start + 1) % 3),
            DecimillipedeSegmentBack(hooks, rng, starter_move_idx=(start + 2) % 3),
        ]
        for seg in segments:
            hp = seg.max_hp
            if hp % 2 == 1:
                hp += 1
            while any(o is not seg and o.max_hp == hp for o in segments):
                hp += 2
                if hp > DecimillipedeSegment.max_hp:
                    hp = DecimillipedeSegment.min_hp
            seg.max_hp = seg.hp = hp
        return segments


DECIMILLIPEDE_ELITE = DecimillipedeEncounter(id="decimillipede_elite")
