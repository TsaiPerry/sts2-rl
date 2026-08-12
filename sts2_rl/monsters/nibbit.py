from __future__ import annotations

import random
from functools import partial
from typing import TYPE_CHECKING

from ..actmap import AscensionLevel
from .base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem

_TRANSITIONS = {"BUTT": "SLICE", "SLICE": "HISS", "HISS": "BUTT"}

_BUTT_DAMAGE = 12       # Nibbit.cs:30 base
_BUTT_DAMAGE_ASC = 13   # DeadlyEnemies
_SLICE_DAMAGE = 6       # Nibbit.cs:34 base
_SLICE_DAMAGE_ASC = 7   # DeadlyEnemies
_SLICE_BLOCK = 5        # Nibbit.cs:32 base
_SLICE_BLOCK_ASC = 6    # ToughEnemies
_HISS_STRENGTH = 2      # Nibbit.cs:36 base
_HISS_STRENGTH_ASC = 3  # DeadlyEnemies


class Nibbit(Monster):
    min_hp = 42
    max_hp = 46
    min_hp_asc = 44   # Nibbit.cs:26 -- ToughEnemies
    max_hp_asc = 48   # Nibbit.cs:28 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None, *, is_front: bool = False, is_alone: bool = False) -> None:
        super().__init__(hooks, rng or random.Random())
        if is_alone:
            self._move_key = "BUTT"
        elif is_front:
            self._move_key = "SLICE"
        else:
            self._move_key = "HISS"

    def _butt_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BUTT_DAMAGE_ASC, _BUTT_DAMAGE)

    def _slice_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLICE_DAMAGE_ASC, _SLICE_DAMAGE)

    def _slice_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _SLICE_BLOCK_ASC, _SLICE_BLOCK)

    def _hiss_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _HISS_STRENGTH_ASC, _HISS_STRENGTH)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "BUTT":
            return Intent(move_type=MoveType.ATTACK, damage=self._butt_dmg(), hits=1)
        if self._move_key == "SLICE":
            return Intent(move_type=MoveType.ATTACK, damage=self._slice_dmg(), hits=1)
        from ..powers import StrengthPower
        return Intent(move_type=MoveType.BUFF, buffs=[(StrengthPower, self._hiss_str())])

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "BUTT":
            self._execute_attack(ctx, self._butt_dmg(), 1)
        elif self._move_key == "SLICE":
            self._execute_attack(ctx, self._slice_dmg(), 1)
            from ..cmds import BlockCmd
            BlockCmd.apply(ctx.hooks, self, self._slice_block())
        else:
            from ..cmds import PowerCmd
            from ..powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, self._hiss_str())
        self._move_key = _TRANSITIONS[self._move_key]


NIBBITS_NORMAL = Encounter(
    id="nibbits_normal",
    monster_classes=[partial(Nibbit, is_front=True), Nibbit],
)

NIBBITS_WEAK = Encounter(
    id="nibbits_weak",
    monster_classes=[partial(Nibbit, is_alone=True)],
)
