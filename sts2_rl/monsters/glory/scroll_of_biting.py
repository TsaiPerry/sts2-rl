from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
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

_CHOMP_DMG = 14         # ScrollOfBiting.cs:41 base
_CHOMP_DMG_ASC = 16     # DeadlyEnemies
_CHEW_DMG = 5           # ScrollOfBiting.cs:43 base
_CHEW_DMG_ASC = 6       # DeadlyEnemies
_CHEW_HITS = 2
_MORE_TEETH_STR = 2
_PAPER_CUTS = 2


class ScrollOfBiting(MachineMonster):
    """Chomp (14) → More Teeth (+2 Strength) → Chew (5×2) → randomly loop back
    to Chomp (cannot repeat) or Chew (at most twice in a row); both branches
    are weight 1. Starts with Paper Cuts 2 (its unblocked hits cost the player
    max HP). Its opening move is set by ``starter_move_idx`` (the encounter
    staggers the three/four scrolls).

    Source: ScrollOfBiting.cs (non-ascension values)."""
    name = "Scroll of Biting"

    min_hp = 30             # ScrollOfBiting.cs:37 base
    max_hp = 37              # ScrollOfBiting.cs:39 base
    min_hp_asc = 33          # ScrollOfBiting.cs:37 -- ToughEnemies
    max_hp_asc = 39          # ScrollOfBiting.cs:39 -- ToughEnemies

    def _chomp_dmg(self) -> int:
        # getattr guard: test_monster_branch_audit._build_machine constructs
        # via cls.__new__(cls) (no __init__, so no _hooks attribute at all)
        # to inspect build_machine()'s pure branch structure -- base value
        # there matches Monster.__init__'s own hooks=None convention.
        hooks = getattr(self, "_hooks", None)
        if hooks is None:
            return _CHOMP_DMG
        return asc_value(hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CHOMP_DMG_ASC, _CHOMP_DMG)

    def _chew_dmg(self) -> int:
        hooks = getattr(self, "_hooks", None)
        if hooks is None:
            return _CHEW_DMG
        return asc_value(hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CHEW_DMG_ASC, _CHEW_DMG)

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
            "CHOMP", self._chomp, Intent(MoveType.ATTACK, damage=self._chomp_dmg())
        )
        chew = MoveState(
            "CHEW", self._chew,
            Intent(MoveType.ATTACK, damage=self._chew_dmg(), hits=_CHEW_HITS),
        )
        more_teeth = MoveState("MORE_TEETH", self._more_teeth, self._more_teeth_intent)
        branch = RandomBranchState("rand")
        chomp.follow_up = more_teeth
        chew.follow_up = branch
        more_teeth.follow_up = chew
        branch.add_branch(chomp, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        # ScrollOfBiting.cs:90 AddBranch(state, 2) is the (state, int
        # maxRepeats) overload — a repeat limit, not a weight.
        branch.add_branch(
            chew, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
        )
        states = [chomp, chew, more_teeth, branch]
        initial = {0: chomp, 1: chew}.get(self._starter_move_idx % 3, more_teeth)
        return MonsterMoveStateMachine(states, initial)

    @staticmethod
    def _more_teeth_intent() -> Intent:
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _MORE_TEETH_STR)])

    def _chomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._chomp_dmg(), 1)

    def _chew(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._chew_dmg(), _CHEW_HITS)

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

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Parity (ScrollsOfBiting{Weak,Normal}.cs:22-23): one
        # `base.Rng.NextInt(3)` on the PER-ENCOUNTER Rng sets the first scroll's
        # StarterMoveIdx. Legacy keeps the shared-rng draw.
        if selection_rng is not None:
            base = selection_rng.next_int(3)
        else:
            base = rng.randint(0, 2)
        idxs = [(base + i) % 3 for i in range(min(self._count, 3))]
        if self._count == 4:
            idxs.append(2)
        return [ScrollOfBiting(hooks, rng, starter_move_idx=i) for i in idxs]


SCROLLS_OF_BITING_WEAK = _ScrollsEncounter("scrolls_of_biting_weak", 3)
SCROLLS_OF_BITING_NORMAL = _ScrollsEncounter("scrolls_of_biting_normal", 4)
