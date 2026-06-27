from __future__ import annotations

import random
from functools import partial
from typing import TYPE_CHECKING

from .base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem

_TRANSITIONS = {"BUTT": "SLICE", "SLICE": "HISS", "HISS": "BUTT"}

_BUTT_DAMAGE = 12
_SLICE_DAMAGE = 6
_SLICE_BLOCK = 5
_HISS_STRENGTH = 2


class Nibbit(Monster):
    min_hp = 42
    max_hp = 46

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None, *, is_front: bool = False, is_alone: bool = False) -> None:
        super().__init__(hooks, rng or random.Random())
        if is_alone:
            self._move_key = "BUTT"
        elif is_front:
            self._move_key = "SLICE"
        else:
            self._move_key = "HISS"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "BUTT":
            return Intent(move_type=MoveType.ATTACK, damage=_BUTT_DAMAGE, hits=1)
        if self._move_key == "SLICE":
            return Intent(move_type=MoveType.ATTACK, damage=_SLICE_DAMAGE, hits=1)
        from ..powers import StrengthPower
        return Intent(move_type=MoveType.BUFF, buffs=[(StrengthPower, _HISS_STRENGTH)])

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "BUTT":
            self._execute_attack(ctx, _BUTT_DAMAGE, 1)
        elif self._move_key == "SLICE":
            self._execute_attack(ctx, _SLICE_DAMAGE, 1)
            from ..cmds import BlockCmd
            BlockCmd.apply(ctx.hooks, self, _SLICE_BLOCK)
        else:
            from ..cmds import PowerCmd
            from ..powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _HISS_STRENGTH)
        self._move_key = _TRANSITIONS[self._move_key]


NIBBITS_NORMAL = Encounter(
    id="nibbits_normal",
    monster_classes=[partial(Nibbit, is_front=True), Nibbit],
)

NIBBITS_WEAK = Encounter(
    id="nibbits_weak",
    monster_classes=[partial(Nibbit, is_alone=True)],
)
