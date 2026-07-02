from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PLOW_DMG = 18
_PLOW_STR = 2
_STOMP_DMG = 15
_CRUSH_DMG = 17
_CRUSH_STR = 3
_PLOW_AMT = 150

# Phase 1: STAMP (apply Plow 150), then PLOW every turn until the Plow power
# breaks (unblocked damage leaves the beast at ≤150 HP — handled by PlowPower,
# which strips all Strength and calls on_plow_broken).
# Phase 2: STUN (skip a turn) → BEAST_CRY → STOMP → CRUSH → BEAST_CRY → ...
_TRANSITIONS = {
    "STAMP": "PLOW",
    "PLOW": "PLOW",
    "STUN": "BEAST_CRY",
    "BEAST_CRY": "STOMP",
    "STOMP": "CRUSH",
    "CRUSH": "BEAST_CRY",
}


class CeremonialBeast(Monster):
    min_hp = 252
    max_hp = 252

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "STAMP"

    def on_plow_broken(self) -> None:
        """Called by PlowPower when unblocked damage drops HP to ≤ the Plow amount."""
        self._move_key = "STUN"

    @property
    def current_intent(self) -> Intent:
        move = self._move_key
        if move == "STAMP":
            from ...powers import PlowPower
            return Intent(MoveType.BUFF, buffs=[(PlowPower, _PLOW_AMT)])
        if move == "PLOW":
            return Intent(MoveType.ATTACK, damage=_PLOW_DMG)
        if move in ("STUN", "BEAST_CRY"):
            return Intent(MoveType.BUFF, buffs=[])
        if move == "STOMP":
            return Intent(MoveType.ATTACK, damage=_STOMP_DMG)
        # CRUSH
        return Intent(MoveType.ATTACK, damage=_CRUSH_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        move = self._move_key
        if move == "STAMP":
            from ...powers import PlowPower
            PowerCmd.apply(ctx.hooks, self, PlowPower, _PLOW_AMT, applier=self)
        elif move == "PLOW":
            self._execute_attack(ctx, _PLOW_DMG, 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _PLOW_STR)
        elif move == "STUN":
            pass  # stunned: do nothing
        elif move == "BEAST_CRY":
            from ...powers import RingingPower
            PowerCmd.apply(ctx.hooks, ctx.player, RingingPower, 1, applier=self)
        elif move == "STOMP":
            self._execute_attack(ctx, _STOMP_DMG, 1)
        else:  # CRUSH
            self._execute_attack(ctx, _CRUSH_DMG, 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _CRUSH_STR)
        # PlowPower may have interrupted the cycle mid-turn (player kills the
        # plow during their turn); only advance if the move wasn't replaced.
        if self._move_key == move:
            self._move_key = _TRANSITIONS[move]


CEREMONIAL_BEAST_BOSS = Encounter(
    id="ceremonial_beast_boss",
    monster_classes=[CeremonialBeast],
)
