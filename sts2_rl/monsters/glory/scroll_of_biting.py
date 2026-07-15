from __future__ import annotations

import random
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

_CHOMP_DMG = 14
_CHEW_DMG = 5
_CHEW_HITS = 2
_MORE_TEETH_STR = 2
_PAPER_CUTS = 2


class ScrollOfBiting(MachineMonster):
    """Chomp (14) → More Teeth (+2 Strength) → Chew (5×2) → randomly loop back
    to Chomp (cannot repeat) or Chew (weight 2). Starts with Paper Cuts 2 (its
    unblocked hits cost the player max HP). Its opening move is set by
    ``starter_move_idx`` (the encounter staggers the three/four scrolls).

    Source: ScrollOfBiting.cs (non-ascension values)."""

    min_hp = 30
    max_hp = 37

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starter_move_idx: int = 0,
    ) -> None:
        self._starter_move_idx = starter_move_idx  # read by build_machine
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PaperCutsPower
        PowerCmd.apply(hooks, self, PaperCutsPower, _PAPER_CUTS)

    def build_machine(self) -> MonsterMoveStateMachine:
        chomp = MoveState(
            "CHOMP", self._chomp, Intent(MoveType.ATTACK, damage=_CHOMP_DMG)
        )
        chew = MoveState(
            "CHEW", self._chew,
            Intent(MoveType.ATTACK, damage=_CHEW_DMG, hits=_CHEW_HITS),
        )
        more_teeth = MoveState("MORE_TEETH", self._more_teeth, self._more_teeth_intent)
        branch = RandomBranchState("rand")
        chomp.follow_up = more_teeth
        chew.follow_up = branch
        more_teeth.follow_up = chew
        branch.add_branch(chomp, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(chew, weight=2.0)
        states = [chomp, chew, more_teeth, branch]
        initial = {0: chomp, 1: chew}.get(self._starter_move_idx % 3, more_teeth)
        return MonsterMoveStateMachine(states, initial)

    @staticmethod
    def _more_teeth_intent() -> Intent:
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _MORE_TEETH_STR)])

    def _chomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CHOMP_DMG, 1)

    def _chew(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CHEW_DMG, _CHEW_HITS)

    def _more_teeth(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _MORE_TEETH_STR)


class _ScrollsEncounter(Encounter):
    """Rolls a random opening move for the first scroll and staggers the rest,
    mirroring ScrollsOfBiting{Weak,Normal}.GenerateMonsters (StarterMoveIdx =
    r, r+1, r+2; the normal fight's 4th scroll always opens on More Teeth)."""

    def __init__(self, id: str, count: int) -> None:  # noqa: A002 - matches base field
        super().__init__(id=id, monster_classes=[ScrollOfBiting] * count)
        self._count = count

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        base = rng.randint(0, 2)
        idxs = [(base + i) % 3 for i in range(min(self._count, 3))]
        if self._count == 4:
            idxs.append(2)
        return [ScrollOfBiting(hooks, rng, starter_move_idx=i) for i in idxs]


SCROLLS_OF_BITING_WEAK = _ScrollsEncounter("scrolls_of_biting_weak", 3)
SCROLLS_OF_BITING_NORMAL = _ScrollsEncounter("scrolls_of_biting_normal", 4)
