from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# SHRINKER once, then CHOMP ↔ STOMP alternating forever.
_TRANSITIONS = {"SHRINKER": "CHOMP", "CHOMP": "STOMP", "STOMP": "CHOMP"}
_CHOMP_DMG = 7
_STOMP_DMG = 13


class ShrinkerBeetle(Monster):
    name = "Shrinker Beetle"
    min_hp = 38
    max_hp = 40

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "SHRINKER"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SHRINKER":
            from ...powers import ShrinkPower
            return Intent(MoveType.DEBUFF, buffs=[(ShrinkPower, -1)])
        if self._move_key == "STOMP":
            return Intent(MoveType.ATTACK, damage=_STOMP_DMG)
        return Intent(MoveType.ATTACK, damage=_CHOMP_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SHRINKER":
            from ...powers import ShrinkPower
            PowerCmd.apply(ctx.hooks, ctx.player, ShrinkPower, -1, applier=self)
        elif self._move_key == "STOMP":
            self._execute_attack(ctx, _STOMP_DMG, 1)
        else:
            self._execute_attack(ctx, _CHOMP_DMG, 1)

    def telegraph_next_move(self) -> None:
        self._move_key = _TRANSITIONS[self._move_key]


SHRINKER_BEETLE_WEAK = Encounter(
    id="shrinker_beetle_weak",
    monster_classes=[ShrinkerBeetle],
)
