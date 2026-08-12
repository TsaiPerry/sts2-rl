from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_FOR_THE_QUEEN_STR = 5
_STRIKE_DOWN_DMG = 21        # FrogKnight.cs:37 base
_STRIKE_DOWN_DMG_ASC = 23    # DeadlyEnemies (asc 9+)
_TONGUE_LASH_DMG = 13        # FrogKnight.cs:39 base
_TONGUE_LASH_DMG_ASC = 14    # DeadlyEnemies (asc 9+)
_TONGUE_LASH_FRAIL = 2
_BEETLE_CHARGE_DMG = 35      # FrogKnight.cs:41 base
_BEETLE_CHARGE_DMG_ASC = 40  # DeadlyEnemies (asc 9+)
_PLATING = 15                # FrogKnight.cs:43 base
_PLATING_ASC = 19            # ToughEnemies (asc 8+)


class FrogKnight(MachineMonster):
    """Tongue Lash (13 + Frail 2) → Strike Down Evil (21) → For the Queen (+5
    Strength) → loop. Once below half HP it makes one Beetle Charge (35) before
    resuming. Starts with Plating 15.

    Source: FrogKnight.cs (non-ascension values)."""
    name = "Frog Knight"

    min_hp = 191
    max_hp = 191
    min_hp_asc = 199     # FrogKnight.cs:33 ToughEnemies (asc 8+)
    max_hp_asc = 199     # FrogKnight.cs:35 `MaxInitialHp => MinInitialHp`

    def _strike_down_dmg(self) -> int:
        """FrogKnight.cs:37 `StrikeDownEvilDamage` -- read at both the
        telegraphed Intent (:71) and the executed attack (:98)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _STRIKE_DOWN_DMG_ASC, _STRIKE_DOWN_DMG)

    def _tongue_lash_dmg(self) -> int:
        """FrogKnight.cs:39 `TongueLashDamage` -- read at both the
        telegraphed Intent (:72) and the executed attack (:106)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _TONGUE_LASH_DMG_ASC, _TONGUE_LASH_DMG)

    def _beetle_charge_dmg(self) -> int:
        """FrogKnight.cs:41 `BeetleChargeDamage` -- read at both the
        telegraphed Intent (:73) and the executed attack (:116)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BEETLE_CHARGE_DMG_ASC, _BEETLE_CHARGE_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._has_beetle_charged = False
        from ...cmds import PowerCmd
        from ...powers import PlatingPower
        # FrogKnight.cs:43 `PlatingAmount` -- read once at AfterAddedToRoom
        # (:63), so it is resolved here rather than via a re-read helper.
        plating = asc_value(hooks, AscensionLevel.TOUGH_ENEMIES,
                             _PLATING_ASC, _PLATING)
        PowerCmd.apply(hooks, self, PlatingPower, plating)

    def build_machine(self) -> MonsterMoveStateMachine:
        for_the_queen = MoveState(
            "FOR_THE_QUEEN", self._for_the_queen, Intent(MoveType.BUFF)
        )
        strike_down = MoveState(
            "STRIKE_DOWN_EVIL", self._strike_down,
            lambda: Intent(MoveType.ATTACK, damage=self._strike_down_dmg()),
        )
        tongue_lash = MoveState(
            "TONGUE_LASH", self._tongue_lash,
            lambda: Intent(MoveType.ATTACK, damage=self._tongue_lash_dmg(), also=(MoveType.DEBUFF,)),
        )
        beetle_charge = MoveState(
            "BEETLE_CHARGE", self._beetle_charge,
            lambda: Intent(MoveType.ATTACK, damage=self._beetle_charge_dmg()),
        )
        branch = ConditionalBranchState("HALF_HEALTH")
        branch.add_state(
            tongue_lash,
            lambda: self._has_beetle_charged or self.hp >= self.max_hp // 2,
        )
        branch.add_state(
            beetle_charge,
            lambda: not self._has_beetle_charged and self.hp < self.max_hp // 2,
        )
        for_the_queen.follow_up = branch
        strike_down.follow_up = for_the_queen
        tongue_lash.follow_up = strike_down
        beetle_charge.follow_up = tongue_lash
        return MonsterMoveStateMachine(
            [branch, for_the_queen, strike_down, tongue_lash, beetle_charge],
            tongue_lash,
        )

    def _for_the_queen(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _FOR_THE_QUEEN_STR)

    def _strike_down(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._strike_down_dmg(), 1)

    def _tongue_lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._tongue_lash_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _TONGUE_LASH_FRAIL)

    def _beetle_charge(self, ctx: CombatCtx) -> None:
        self._has_beetle_charged = True
        self._execute_attack(ctx, self._beetle_charge_dmg(), 1)


FROG_KNIGHT_NORMAL = Encounter(
    id="frog_knight_normal",
    monster_classes=[FrogKnight],
)
