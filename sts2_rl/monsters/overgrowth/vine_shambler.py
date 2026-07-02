from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_TRANSITIONS = {"SWIPE": "GRASPING_VINES", "GRASPING_VINES": "CHOMP", "CHOMP": "SWIPE"}
_SWIPE_DMG = 6
_SWIPE_HITS = 2
_GRASPING_DMG = 8
_CHOMP_DMG = 16


class VineShambler(Monster):
    min_hp = 61
    max_hp = 61

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "SWIPE"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SWIPE":
            return Intent(MoveType.ATTACK, damage=_SWIPE_DMG, hits=_SWIPE_HITS)
        if self._move_key == "GRASPING_VINES":
            return Intent(MoveType.ATTACK, damage=_GRASPING_DMG)
        return Intent(MoveType.ATTACK, damage=_CHOMP_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SWIPE":
            self._execute_attack(ctx, _SWIPE_DMG, _SWIPE_HITS)
        elif self._move_key == "GRASPING_VINES":
            self._execute_attack(ctx, _GRASPING_DMG, 1)
            from ...powers import TangledPower
            PowerCmd.apply(ctx.hooks, ctx.player, TangledPower, 1)
        else:
            self._execute_attack(ctx, _CHOMP_DMG, 1)
        self._move_key = _TRANSITIONS[self._move_key]


VINE_SHAMBLER_NORMAL = Encounter(
    id="vine_shambler_normal",
    monster_classes=[VineShambler],
)
