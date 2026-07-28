from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_INK_BLOT_DMG = 7
_INKY_LANCE_DMG = 6
_INKY_LANCE_HITS = 2
_DISMEMBER_DMG = 26
_PREPARE_STR = 2
_SLIPPERY_START = 8

_TRANSITIONS = {
    "INK_BLOT": "INKY_LANCE",
    "INKY_LANCE": "DISMEMBER",
    "DISMEMBER": "PREPARE",
    "PREPARE": "INK_BLOT",
}


class Vantom(Monster):
    min_hp = 173
    max_hp = 173

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SlipperyPower
        PowerCmd.apply(hooks, self, SlipperyPower, _SLIPPERY_START)
        self._move_key = "INK_BLOT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "INK_BLOT":
            return Intent(MoveType.ATTACK, damage=_INK_BLOT_DMG)
        if self._move_key == "INKY_LANCE":
            return Intent(MoveType.ATTACK, damage=_INKY_LANCE_DMG, hits=_INKY_LANCE_HITS)
        if self._move_key == "DISMEMBER":
            # Vantom.cs:119 — SingleAttackIntent(26) AND StatusIntent(3).
            return Intent(MoveType.ATTACK, damage=_DISMEMBER_DMG,
                          also=(MoveType.STATUS_CARD,))
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _PREPARE_STR)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "INK_BLOT":
            self._execute_attack(ctx, _INK_BLOT_DMG, 1)
        elif self._move_key == "INKY_LANCE":
            self._execute_attack(ctx, _INKY_LANCE_DMG, _INKY_LANCE_HITS)
        elif self._move_key == "DISMEMBER":
            self._execute_attack(ctx, _DISMEMBER_DMG, 1)
            from ...cards import WoundCard
            from ...cmds import CardPileCmd
            for _ in range(3):
                CardPileCmd.add_to_discard(ctx.hooks, ctx.player, WoundCard())
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _PREPARE_STR)
        self._move_key = _TRANSITIONS[self._move_key]


VANTOM_BOSS = Encounter(
    id="vantom_boss",
    monster_classes=[Vantom],
)
