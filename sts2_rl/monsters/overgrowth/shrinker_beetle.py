from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# SHRINKER once, then CHOMP ↔ STOMP alternating forever.
_TRANSITIONS = {"SHRINKER": "CHOMP", "CHOMP": "STOMP", "STOMP": "CHOMP"}
_CHOMP_DMG = 7          # ShrinkerBeetle.cs:25 base
_CHOMP_DMG_ASC = 8      # DeadlyEnemies
_STOMP_DMG = 13         # ShrinkerBeetle.cs:27 base
_STOMP_DMG_ASC = 14     # DeadlyEnemies


class ShrinkerBeetle(Monster):
    name = "Shrinker Beetle"
    min_hp = 38              # ShrinkerBeetle.cs:21 base
    max_hp = 40                # ShrinkerBeetle.cs:23 base
    min_hp_asc = 40             # ShrinkerBeetle.cs:21 -- ToughEnemies
    max_hp_asc = 42             # ShrinkerBeetle.cs:23 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "SHRINKER"

    def _chomp_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CHOMP_DMG_ASC, _CHOMP_DMG)

    def _stomp_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _STOMP_DMG_ASC, _STOMP_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SHRINKER":
            from ...powers import ShrinkPower
            return Intent(MoveType.DEBUFF, buffs=[(ShrinkPower, -1)])
        if self._move_key == "STOMP":
            return Intent(MoveType.ATTACK, damage=self._stomp_dmg())
        return Intent(MoveType.ATTACK, damage=self._chomp_dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SHRINKER":
            from ...powers import ShrinkPower
            PowerCmd.apply(ctx.hooks, ctx.player, ShrinkPower, -1, applier=self)
        elif self._move_key == "STOMP":
            self._execute_attack(ctx, self._stomp_dmg(), 1)
        else:
            self._execute_attack(ctx, self._chomp_dmg(), 1)

    def telegraph_next_move(self) -> None:
        self._move_key = _TRANSITIONS[self._move_key]


SHRINKER_BEETLE_WEAK = Encounter(
    id="shrinker_beetle_weak",
    monster_classes=[ShrinkerBeetle],
)
