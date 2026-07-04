"""Entomancer (Hive elite). Sources: Entomancer.cs, EntomancerElite.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SPEAR_DMG = 18
_BEES_DMG = 3
_BEES_HITS = 7
_MAX_HIVE = 3


class Entomancer(MachineMonster):
    """Spawns with Personal Hive 1 (every powered hit on it shuffles Dazed
    into your draw pile). Cycle: BEES (3x7) → SPEAR (18) → PHEROMONE_SPIT
    (grow the hive +1 and +1 Strength while the hive is below 3, else +2
    Strength)."""

    min_hp = 145
    max_hp = 145

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PersonalHivePower
        PowerCmd.apply(hooks, self, PersonalHivePower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        spit = MoveState("PHEROMONE_SPIT_MOVE", self._spit, Intent(MoveType.BUFF))
        bees = MoveState(
            "BEES_MOVE", self._bees,
            Intent(MoveType.ATTACK, damage=_BEES_DMG, hits=_BEES_HITS),
        )
        spear = MoveState(
            "SPEAR_MOVE", self._spear, Intent(MoveType.ATTACK, damage=_SPEAR_DMG)
        )
        bees.follow_up = spear
        spear.follow_up = spit
        spit.follow_up = bees
        return MonsterMoveStateMachine([spit, bees, spear], bees)

    def _spit(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import PersonalHivePower, StrengthPower
        hive = self.powers.get("personal_hive")
        if hive is not None and hive.amount < _MAX_HIVE:
            PowerCmd.apply(ctx.hooks, self, PersonalHivePower, 1)
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 1)
        else:
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 2)

    def _bees(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BEES_DMG, _BEES_HITS)

    def _spear(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SPEAR_DMG, 1)


ENTOMANCER_ELITE = Encounter(
    id="entomancer_elite",
    monster_classes=[Entomancer],
)
