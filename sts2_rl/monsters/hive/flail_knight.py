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
    from ...hooks import HookSystem

_WAR_CHANT_STRENGTH = 3
_FLAIL_DMG = 9          # FlailKnight.cs:38 base
_FLAIL_DMG_ASC = 10     # DeadlyEnemies (asc 9+)
_FLAIL_HITS = 2
_RAM_DMG = 15           # FlailKnight.cs:40 base
_RAM_DMG_ASC = 17       # DeadlyEnemies (asc 9+)
_KNIGHT_STRENGTH = 6
_KNIGHT_PLATING = 6


class FlailKnight(MachineMonster):
    """Starts with RAM (15), then each turn picks among WAR_CHANT (+3 Strength,
    cannot repeat), FLAIL (9×2) and RAM (15) — the last two at most twice in a
    row (all three weight 1).

    Source: FlailKnight.cs (non-ascension values)."""
    name = "Flail Knight"

    min_hp = 101          # FlailKnight.cs:32-34
    max_hp = 101
    min_hp_asc = 108       # ToughEnemies (asc 8+); MaxInitialHp = MinInitialHp
    max_hp_asc = 108

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _flail_dmg(self) -> int:
        """FlailKnight.cs:38 `FlailDamage` -- a C# PROPERTY re-read at both the
        telegraphed Intent (:46) and the executed attack (:68)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _FLAIL_DMG_ASC, _FLAIL_DMG)

    def _ram_dmg(self) -> int:
        """FlailKnight.cs:40 `RamDamage` -- a C# PROPERTY re-read at both the
        telegraphed Intent (:47) and the executed attack (:78)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RAM_DMG_ASC, _RAM_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        war_chant = MoveState("WAR_CHANT", self._war_chant, self._war_chant_intent)
        flail = MoveState(
            "FLAIL_MOVE", self._flail,
            lambda: Intent(MoveType.ATTACK, damage=self._flail_dmg(), hits=_FLAIL_HITS),
        )
        ram = MoveState(
            "RAM_MOVE", self._ram,
            lambda: Intent(MoveType.ATTACK, damage=self._ram_dmg()),
        )
        branch = RandomBranchState("RAND")
        branch.add_branch(war_chant, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        # FlailKnight.cs:50-51 AddBranch(state, 2) is the (state, int
        # maxRepeats) overload — a repeat limit, not a weight.
        branch.add_branch(
            flail, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
        )
        branch.add_branch(
            ram, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
        )
        war_chant.follow_up = branch
        flail.follow_up = branch
        ram.follow_up = branch
        return MonsterMoveStateMachine([war_chant, flail, ram, branch], ram)

    @staticmethod
    def _war_chant_intent() -> Intent:
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _WAR_CHANT_STRENGTH)])

    def _war_chant(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _WAR_CHANT_STRENGTH)

    def _flail(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._flail_dmg(), _FLAIL_HITS)

    def _ram(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._ram_dmg(), 1)


class MysteriousKnight(FlailKnight):
    """A Flail Knight that starts with 6 Strength and 6 Plating.

    Source: MysteriousKnight.cs — AfterAddedToRoom applies StrengthPower 6 and
    PlatingPower 6. Fought in The Lantern Key event."""
    name = "Mysterious Knight"

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PlatingPower, StrengthPower
        PowerCmd.apply(hooks, self, StrengthPower, _KNIGHT_STRENGTH)
        PowerCmd.apply(hooks, self, PlatingPower, _KNIGHT_PLATING)


MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER = Encounter(
    id="mysterious_knight_event",
    monster_classes=[MysteriousKnight],
    # C# class MysteriousKnightEventEncounter — the sim id drops the suffix.
    entry_slug="MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER",
)
