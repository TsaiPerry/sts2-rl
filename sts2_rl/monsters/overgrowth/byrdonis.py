from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PECK_DMG = 3           # Byrdonis.cs:24 base
_PECK_DMG_ASC = 4       # DeadlyEnemies (asc 9+)
# Byrdonis.cs:26 `PeckRepeat` reads GetValueIfAscension(DeadlyEnemies, 3, 3)
# -- degenerate, asc value equals base; ported as a no-op comment only.
_PECK_HITS = 3
_SWOOP_DMG = 17         # Byrdonis.cs:28 base
_SWOOP_DMG_ASC = 19     # DeadlyEnemies (asc 9+)


class Byrdonis(MachineMonster):
    """SWOOP → PECK → SWOOP → ... (a fixed two-move loop, as in the source)."""

    min_hp = 81
    max_hp = 84
    # Byrdonis.cs:20-22 -- MinInitialHp/MaxInitialHp read GetValueIfAscension
    # (ToughEnemies, 90, 81/84).
    min_hp_asc = 90
    max_hp_asc = 90

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import TerritorialPower
        PowerCmd.apply(hooks, self, TerritorialPower, 1)

    def _peck_dmg(self) -> int:
        """Byrdonis.cs:24 `PeckDamage` -- re-read at both the telegraphed
        Intent (build_machine) and the executed attack (_peck)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PECK_DMG_ASC, _PECK_DMG)

    def _swoop_dmg(self) -> int:
        """Byrdonis.cs:28 `SwoopDamage` -- re-read at both the telegraphed
        Intent (build_machine) and the executed attack (_swoop)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SWOOP_DMG_ASC, _SWOOP_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        swoop = MoveState(
            "SWOOP_MOVE", self._swoop,
            lambda: Intent(MoveType.ATTACK, damage=self._swoop_dmg()),
        )
        peck = MoveState(
            "PECK_MOVE", self._peck,
            lambda: Intent(MoveType.ATTACK, damage=self._peck_dmg(), hits=_PECK_HITS),
        )
        swoop.follow_up = peck
        peck.follow_up = swoop
        return MonsterMoveStateMachine([swoop, peck], swoop)

    def _swoop(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._swoop_dmg(), 1)

    def _peck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._peck_dmg(), _PECK_HITS)


BYRDONIS_ELITE = Encounter(
    id="byrdonis_elite",
    monster_classes=[Byrdonis],
)
