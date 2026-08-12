from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_TRANSITIONS = {"SWIPE": "GRASPING_VINES", "GRASPING_VINES": "CHOMP", "CHOMP": "SWIPE"}
_SWIPE_DMG = 6          # VineShambler.cs:40 base
_SWIPE_DMG_ASC = 7      # DeadlyEnemies (asc 9+)
_SWIPE_HITS = 2
_GRASPING_DMG = 8       # VineShambler.cs:38 base
_GRASPING_DMG_ASC = 9   # DeadlyEnemies (asc 9+)
_CHOMP_DMG = 16         # VineShambler.cs:42 base
_CHOMP_DMG_ASC = 18     # DeadlyEnemies (asc 9+)


class VineShambler(Monster):
    name = "Vine Shambler"
    min_hp = 61          # VineShambler.cs:34 base (MaxInitialHp == MinInitialHp)
    max_hp = 61
    min_hp_asc = 64       # VineShambler.cs:34 ToughEnemies (asc 8+)
    max_hp_asc = 64

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "SWIPE"

    def _swipe_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SWIPE_DMG_ASC, _SWIPE_DMG)

    def _grasping_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _GRASPING_DMG_ASC, _GRASPING_DMG)

    def _chomp_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CHOMP_DMG_ASC, _CHOMP_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "SWIPE":
            return Intent(MoveType.ATTACK, damage=self._swipe_dmg(), hits=_SWIPE_HITS)
        if self._move_key == "GRASPING_VINES":
            # VineShambler.cs:47 — SingleAttackIntent(8) AND CardDebuffIntent.
            return Intent(MoveType.ATTACK, damage=self._grasping_dmg(),
                          also=(MoveType.CARD_DEBUFF,))
        return Intent(MoveType.ATTACK, damage=self._chomp_dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "SWIPE":
            self._execute_attack(ctx, self._swipe_dmg(), _SWIPE_HITS)
        elif self._move_key == "GRASPING_VINES":
            self._execute_attack(ctx, self._grasping_dmg(), 1)
            from ...powers import TangledPower
            PowerCmd.apply(ctx.hooks, ctx.player, TangledPower, 1)
        else:
            self._execute_attack(ctx, self._chomp_dmg(), 1)
        self._move_key = _TRANSITIONS[self._move_key]


VINE_SHAMBLER_NORMAL = Encounter(
    id="vine_shambler_normal",
    monster_classes=[VineShambler],
)
