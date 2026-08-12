from __future__ import annotations

import random
from functools import partial
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
from ..state_machine import weighted_branch_pick

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JAB_DMG = 3                 # Inklet.cs:34 base
_JAB_DMG_ASC = 4             # DeadlyEnemies (asc 9+)
_WHIRLWIND_DMG = 2           # Inklet.cs:36 base
_WHIRLWIND_DMG_ASC = 3       # DeadlyEnemies (asc 9+)
_WHIRLWIND_HITS = 3
_PIERCING_DMG = 10           # Inklet.cs:38 base
_PIERCING_DMG_ASC = 11       # DeadlyEnemies (asc 9+)


class Inklet(Monster):
    min_hp = 11
    max_hp = 17
    min_hp_asc = 12          # Inklet.cs:30 ToughEnemies (asc 8+)
    max_hp_asc = 18          # Inklet.cs:32 ToughEnemies (asc 8+)

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        is_middle: bool = False,
    ) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SlipperyPower
        PowerCmd.apply(hooks, self, SlipperyPower, 1, applier=self)
        self._rng = rng or random.Random()
        self._move_key = "WHIRLWIND" if is_middle else "JAB"

    def _jab_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _JAB_DMG_ASC, _JAB_DMG)

    def _whirlwind_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _WHIRLWIND_DMG_ASC, _WHIRLWIND_DMG)

    def _piercing_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PIERCING_DMG_ASC, _PIERCING_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "JAB":
            return Intent(MoveType.ATTACK, damage=self._jab_dmg())
        if self._move_key == "WHIRLWIND":
            return Intent(MoveType.ATTACK, damage=self._whirlwind_dmg(), hits=_WHIRLWIND_HITS)
        return Intent(MoveType.ATTACK, damage=self._piercing_dmg())  # PIERCING_GAZE

    def take_turn(self, ctx: CombatCtx) -> None:
        move = self._move_key
        if move == "JAB":
            self._execute_attack(ctx, self._jab_dmg(), 1)
        elif move == "WHIRLWIND":
            self._execute_attack(ctx, self._whirlwind_dmg(), _WHIRLWIND_HITS)
        else:
            self._execute_attack(ctx, self._piercing_dmg(), 1)

    def telegraph_next_move(self) -> None:
        self._move_key = self._next_move(self._move_key)

    def _next_move(self, current: str) -> str:
        if current == "JAB":
            # 50/50 between PIERCING_GAZE and WHIRLWIND. The ADD ORDER is
            # observable even at equal weights — the walk subtracts in add
            # order and returns the first branch at num <= 0 — and Inklet.cs:73
            # adds PIERCING_GAZE_MOVE before WHIRLWIND_MOVE.
            return weighted_branch_pick(
                self._hooks.combat.combat_rng.monster_ai,
                ["PIERCING_GAZE", "WHIRLWIND"], [1, 1],
            )
        # WHIRLWIND and PIERCING_GAZE both return to JAB
        return "JAB"


INKLETS_NORMAL = Encounter(
    id="inklets_normal",
    monster_classes=[Inklet, partial(Inklet, is_middle=True), Inklet],
)
