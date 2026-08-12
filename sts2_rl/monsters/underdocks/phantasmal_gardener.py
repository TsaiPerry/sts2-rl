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

# BiteDamage (PhantasmalGardener.cs:39) reads GetValueIfAscension(
# DeadlyEnemies, 5, 5) -- both branches 5, a no-op; ported as a comment only.
_BITE_DMG = 5
# LashDamage (:41) reads GetValueIfAscension(DeadlyEnemies, 7, 7) -- both
# branches 7, a no-op; ported as a comment only.
_LASH_DMG = 7
_FLAIL_DMG = 1
# FlailRepeat (:45) reads GetValueIfAscension(DeadlyEnemies, 3, 3) -- both
# branches 3, a no-op; ported as a comment only.
_FLAIL_HITS = 3
_ENLARGE_STR = 2         # PhantasmalGardener.cs:47 base
_ENLARGE_STR_ASC = 3     # DeadlyEnemies
_SKITTISH_BLOCK = 6      # PhantasmalGardener.cs:49 base
_SKITTISH_BLOCK_ASC = 7  # ToughEnemies

_SLOTS = ("first", "second", "third", "fourth")


class PhantasmalGardener(MachineMonster):
    """BITE → LASH → FLAIL → ENLARGE → loop; each gardener enters the cycle at
    a different point based on its slot (first→FLAIL, second→BITE,
    third→LASH, fourth→ENLARGE). Skittish 6: the first card attack each turn
    that deals it unblocked damage grants 6 block."""
    name = "Phantasmal Gardener"

    min_hp = 26
    max_hp = 31
    min_hp_asc = 27   # PhantasmalGardener.cs:35 -- ToughEnemies
    max_hp_asc = 32   # PhantasmalGardener.cs:37 -- ToughEnemies

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        slot: str = "first",
    ) -> None:
        self.slot = slot  # read by build_machine
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SkittishPower
        skittish = asc_value(hooks, AscensionLevel.TOUGH_ENEMIES,
                              _SKITTISH_BLOCK_ASC, _SKITTISH_BLOCK)
        PowerCmd.apply(hooks, self, SkittishPower, skittish)

    def _enlarge_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ENLARGE_STR_ASC, _ENLARGE_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        bite = MoveState(
            "BITE_MOVE", self._bite, Intent(MoveType.ATTACK, damage=_BITE_DMG)
        )
        lash = MoveState(
            "LASH_MOVE", self._lash, Intent(MoveType.ATTACK, damage=_LASH_DMG)
        )
        flail = MoveState(
            "FLAIL_MOVE", self._flail,
            Intent(MoveType.ATTACK, damage=_FLAIL_DMG, hits=_FLAIL_HITS),
        )
        enlarge = MoveState("ENLARGE_MOVE", self._enlarge, Intent(MoveType.BUFF))
        init = ConditionalBranchState("INIT_MOVE")
        init.add_state(flail, lambda: self.slot == "first")
        init.add_state(bite, lambda: self.slot == "second")
        init.add_state(lash, lambda: self.slot == "third")
        init.add_state(enlarge, lambda: self.slot == "fourth")
        bite.follow_up = lash
        lash.follow_up = flail
        flail.follow_up = enlarge
        enlarge.follow_up = bite
        return MonsterMoveStateMachine([bite, lash, enlarge, flail, init], init)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LASH_DMG, 1)

    def _flail(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _FLAIL_DMG, _FLAIL_HITS)

    def _enlarge(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._enlarge_str())


@dataclass
class PhantasmalGardenersEncounter(Encounter):
    """Four gardeners in slots first..fourth."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [PhantasmalGardener(hooks, rng, slot=slot) for slot in _SLOTS]


PHANTASMAL_GARDENERS_ELITE = PhantasmalGardenersEncounter(
    id="phantasmal_gardeners_elite"
)
