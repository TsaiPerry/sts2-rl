from __future__ import annotations

import random
from functools import partial
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_JAB_DMG = 3
_WHIRLWIND_DMG = 2
_WHIRLWIND_HITS = 3
_PIERCING_DMG = 10


class Inklet(Monster):
    min_hp = 11
    max_hp = 17

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

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "JAB":
            return Intent(MoveType.ATTACK, damage=_JAB_DMG)
        if self._move_key == "WHIRLWIND":
            return Intent(MoveType.ATTACK, damage=_WHIRLWIND_DMG, hits=_WHIRLWIND_HITS)
        return Intent(MoveType.ATTACK, damage=_PIERCING_DMG)  # PIERCING_GAZE

    def take_turn(self, ctx: CombatCtx) -> None:
        move = self._move_key
        if move == "JAB":
            self._execute_attack(ctx, _JAB_DMG, 1)
        elif move == "WHIRLWIND":
            self._execute_attack(ctx, _WHIRLWIND_DMG, _WHIRLWIND_HITS)
        else:
            self._execute_attack(ctx, _PIERCING_DMG, 1)
        self._move_key = self._next_move(move)

    def _next_move(self, current: str) -> str:
        if current == "JAB":
            # 50/50 between PIERCING_GAZE and WHIRLWIND
            return self._rng.choice(["WHIRLWIND", "PIERCING_GAZE"])
        # WHIRLWIND and PIERCING_GAZE both return to JAB
        return "JAB"


INKLETS_NORMAL = Encounter(
    id="inklets_normal",
    monster_classes=[Inklet, partial(Inklet, is_middle=True), Inklet],
)
