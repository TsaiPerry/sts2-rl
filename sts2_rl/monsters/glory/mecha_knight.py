from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_CHARGE_DMG = 25
_FLAMETHROWER_BURN = 4
_WINDUP_BLOCK = 15
_WINDUP_STR = 5
_HEAVY_CLEAVE_DMG = 35
_ARTIFACT = 3


class MechaKnight(MachineMonster):
    """Charge (25) → Flamethrower (4 Burn to hand) → Wind Up (15 block + 5
    Strength) → Heavy Cleave (35) → loop back to Flamethrower. Starts with
    Artifact 3.

    Source: MechaKnight.cs (non-ascension values)."""

    min_hp = 300
    max_hp = 300

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ArtifactPower
        PowerCmd.apply(hooks, self, ArtifactPower, _ARTIFACT)

    def build_machine(self) -> MonsterMoveStateMachine:
        charge = MoveState(
            "CHARGE_MOVE", self._charge, Intent(MoveType.ATTACK, damage=_CHARGE_DMG)
        )
        flamethrower = MoveState(
            "FLAMETHROWER_MOVE", self._flamethrower, Intent(MoveType.STATUS_CARD)
        )
        windup = MoveState(
            "WINDUP_MOVE", self._windup,
            Intent(MoveType.DEFEND, also=(MoveType.BUFF,)),
        )
        heavy_cleave = MoveState(
            "HEAVY_CLEAVE_MOVE", self._heavy_cleave,
            Intent(MoveType.ATTACK, damage=_HEAVY_CLEAVE_DMG),
        )
        charge.follow_up = flamethrower
        flamethrower.follow_up = windup
        windup.follow_up = heavy_cleave
        heavy_cleave.follow_up = flamethrower
        return MonsterMoveStateMachine(
            [charge, heavy_cleave, windup, flamethrower], charge
        )

    def _charge(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CHARGE_DMG, 1)

    def _flamethrower(self, ctx: CombatCtx) -> None:
        from ...cards import BurnCard
        from ...cmds import CardPileCmd
        for _ in range(_FLAMETHROWER_BURN):
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, BurnCard())

    def _windup(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, _WINDUP_BLOCK, props=ValueProp.MOVE)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _WINDUP_STR)

    def _heavy_cleave(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HEAVY_CLEAVE_DMG, 1)


MECHA_KNIGHT_ELITE = Encounter(
    id="mecha_knight_elite",
    monster_classes=[MechaKnight],
)
