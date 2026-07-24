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
# which strips all Strength and calls on_plow_broken, stunning the beast).
# Phase 2 (after the stunned turn): BEAST_CRY → STOMP → CRUSH → BEAST_CRY → ...
_TRANSITIONS = {
    "STAMP": "PLOW",
    "PLOW": "PLOW",
    "BEAST_CRY": "STOMP",
    "STOMP": "CRUSH",
    "CRUSH": "BEAST_CRY",
}


class CeremonialBeast(Monster):
    name = "Ceremonial Beast"
    min_hp = 252
    max_hp = 252

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "STAMP"

    def on_plow_broken(self) -> None:
        """Called by PlowPower when unblocked damage drops HP to ≤ the Plow amount.
        The beast skips a turn, then enters phase 2 at BEAST_CRY."""
        from ...cmds import CreatureCmd
        CreatureCmd.stun(self._hooks, self, next_move_key="BEAST_CRY")

    @property
    def current_intent(self) -> Intent:
        if self.stunned:
            return Intent(MoveType.STUN)
        move = self._move_key
        if move == "STAMP":
            from ...powers import PlowPower
            return Intent(MoveType.BUFF, buffs=[(PlowPower, _PLOW_AMT)])
        if move == "PLOW":
            return Intent(MoveType.ATTACK, damage=_PLOW_DMG)
        if move == "BEAST_CRY":
            return Intent(MoveType.CARD_DEBUFF)  # Ringing afflicts the player's cards
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
        elif move == "BEAST_CRY":
            from ...powers import RingingPower
            PowerCmd.apply(ctx.hooks, ctx.player, RingingPower, 1, applier=self)
        elif move == "STOMP":
            self._execute_attack(ctx, _STOMP_DMG, 1)
        else:  # CRUSH
            self._execute_attack(ctx, _CRUSH_DMG, 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _CRUSH_STR)
        # PlowPower may have interrupted the cycle mid-turn (the plow breaking
        # stuns the beast and redirects to BEAST_CRY); only advance if the
        # move wasn't replaced.
        if self._move_key == move:
            self._move_key = _TRANSITIONS[move]


CEREMONIAL_BEAST_BOSS = Encounter(
    id="ceremonial_beast_boss",
    monster_classes=[CeremonialBeast],
)
