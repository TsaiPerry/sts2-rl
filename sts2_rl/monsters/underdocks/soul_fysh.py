from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_DE_GAS_DMG = 16
_GAZE_DMG = 7
_SCREAM_DMG = 13
_SCREAM_VULN = 3
_FADE_INTANGIBLE = 2
_BECKON_COUNT = 2


class SoulFysh(MachineMonster):
    """Underdocks boss. Fixed loop: BECKON (a Beckon status into the draw
    pile and one into the discard) → DE_GAS (16) → GAZE (7 + a Beckon into
    the discard) → FADE (Intangible 2) → SCREAM (13 + Vulnerable 3)."""

    min_hp = 211
    max_hp = 211

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        beckon = MoveState(
            "BECKON_MOVE", self._beckon, Intent(MoveType.STATUS_CARD)
        )
        de_gas = MoveState(
            "DE_GAS_MOVE", self._de_gas,
            Intent(MoveType.ATTACK, damage=_DE_GAS_DMG),
        )
        gaze = MoveState(
            "GAZE_MOVE", self._gaze,
            Intent(MoveType.ATTACK, damage=_GAZE_DMG,
                   also=(MoveType.STATUS_CARD,)),
        )
        fade = MoveState("FADE_MOVE", self._fade, Intent(MoveType.BUFF))
        scream = MoveState(
            "SCREAM_MOVE", self._scream,
            Intent(MoveType.ATTACK, damage=_SCREAM_DMG,
                   also=(MoveType.DEBUFF,)),
        )
        beckon.follow_up = de_gas
        de_gas.follow_up = gaze
        gaze.follow_up = fade
        fade.follow_up = scream
        scream.follow_up = beckon
        return MonsterMoveStateMachine(
            [beckon, de_gas, gaze, scream, fade], beckon
        )

    def _beckon(self, ctx: CombatCtx) -> None:
        from ...cards import make_card
        from ...cmds import CardPileCmd
        CardPileCmd.add_to_draw(ctx.hooks, ctx.player, make_card("beckon"))
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, make_card("beckon"))

    def _de_gas(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _DE_GAS_DMG, 1)

    def _gaze(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _GAZE_DMG, 1)
        from ...cards import make_card
        from ...cmds import CardPileCmd
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, make_card("beckon"))

    def _fade(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import IntangiblePower
        PowerCmd.apply(ctx.hooks, self, IntangiblePower, _FADE_INTANGIBLE)

    def _scream(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SCREAM_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _SCREAM_VULN)


SOUL_FYSH_BOSS = Encounter(
    id="soul_fysh_boss",
    monster_classes=[SoulFysh],
)
