from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PLOW_DMG = 18          # CeremonialBeast.cs:61 base
_PLOW_DMG_ASC = 20      # DeadlyEnemies
_PLOW_STR = 2           # CeremonialBeast.cs:63 -- not ascension-gated
_STOMP_DMG = 15         # CeremonialBeast.cs:65 base
_STOMP_DMG_ASC = 17     # DeadlyEnemies
_CRUSH_DMG = 17         # CeremonialBeast.cs:67 base
_CRUSH_DMG_ASC = 19     # DeadlyEnemies
_CRUSH_STR = 3          # CeremonialBeast.cs:69 base
_CRUSH_STR_ASC = 4      # DeadlyEnemies
_PLOW_AMT = 150         # CeremonialBeast.cs:59 base
_PLOW_AMT_ASC = 160     # DeadlyEnemies

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
    min_hp = 252          # CeremonialBeast.cs:55
    max_hp = 252
    min_hp_asc = 262       # CeremonialBeast.cs:55 -- ToughEnemies
    max_hp_asc = 262

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "STAMP"

    def _plow_amount(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _PLOW_AMT_ASC, _PLOW_AMT)

    def _plow_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _PLOW_DMG_ASC, _PLOW_DMG)

    def _stomp_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _STOMP_DMG_ASC, _STOMP_DMG)

    def _crush_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _CRUSH_DMG_ASC, _CRUSH_DMG)

    def _crush_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, _CRUSH_STR_ASC, _CRUSH_STR)

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
            return Intent(MoveType.BUFF, buffs=[(PlowPower, self._plow_amount())])
        if move == "PLOW":
            # Attack + Buff: the game's PLOW_MOVE telegraphs BOTH
            # (`new SingleAttackIntent(PlowDamage), new BuffIntent()`,
            # CeremonialBeast.cs:147 — the post-hit +2 Strength).
            from ...powers import StrengthPower
            return Intent(MoveType.ATTACK, damage=self._plow_dmg(),
                          also=[MoveType.BUFF],
                          buffs=[(StrengthPower, _PLOW_STR)])
        if move == "BEAST_CRY":
            return Intent(MoveType.CARD_DEBUFF)  # Ringing afflicts the player's cards
        if move == "STOMP":
            return Intent(MoveType.ATTACK, damage=self._stomp_dmg())
        # CRUSH — Attack + Buff, same shape as PLOW (CeremonialBeast.cs:154).
        from ...powers import StrengthPower
        return Intent(MoveType.ATTACK, damage=self._crush_dmg(),
                      also=[MoveType.BUFF],
                      buffs=[(StrengthPower, self._crush_str())])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        move = self._move_key
        if move == "STAMP":
            from ...powers import PlowPower
            PowerCmd.apply(ctx.hooks, self, PlowPower, self._plow_amount(), applier=self)
        elif move == "PLOW":
            self._execute_attack(ctx, self._plow_dmg(), 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _PLOW_STR)
        elif move == "BEAST_CRY":
            from ...powers import RingingPower
            PowerCmd.apply(ctx.hooks, ctx.player, RingingPower, 1, applier=self)
        elif move == "STOMP":
            self._execute_attack(ctx, self._stomp_dmg(), 1)
        else:  # CRUSH
            self._execute_attack(ctx, self._crush_dmg(), 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, self._crush_str())
        # PlowPower may have interrupted the cycle mid-turn (the plow breaking
        # stuns the beast and redirects to BEAST_CRY); only advance if the
        # move wasn't replaced.
        if self._move_key == move:
            self._move_key = _TRANSITIONS[move]


CEREMONIAL_BEAST_BOSS = Encounter(
    id="ceremonial_beast_boss",
    monster_classes=[CeremonialBeast],
)
