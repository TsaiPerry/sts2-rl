"""Louse Progenitor (Hive). Sources: LouseProgenitor.cs,
LouseProgenitorNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_WEB_DMG = 9
_WEB_FRAIL = 2
_POUNCE_DMG = 14
_CURL_BLOCK = 14
_GROW_STR = 5


class LouseProgenitor(MachineMonster):
    """Spawns with Curl Up 14 (blocks when first hit). Cycle: WEB_CANNON
    (9 + Frail 2) → CURL_AND_GROW (14 block + 5 Strength) → POUNCE (14)."""
    name = "Louse Progenitor"

    min_hp = 134
    max_hp = 136

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import CurlUpPower
        PowerCmd.apply(hooks, self, CurlUpPower, _CURL_BLOCK)

    def build_machine(self) -> MonsterMoveStateMachine:
        web = MoveState(
            "WEB_CANNON_MOVE", self._web,
            Intent(MoveType.ATTACK, damage=_WEB_DMG, also=(MoveType.DEBUFF,)),
        )
        curl = MoveState(
            "CURL_AND_GROW_MOVE", self._curl_and_grow,
            Intent(MoveType.DEFEND, also=(MoveType.BUFF,)),
        )
        pounce = MoveState(
            "POUNCE_MOVE", self._pounce, Intent(MoveType.ATTACK, damage=_POUNCE_DMG)
        )
        web.follow_up = curl
        curl.follow_up = pounce
        pounce.follow_up = web
        return MonsterMoveStateMachine([curl, web, pounce], web)

    def _web(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WEB_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _WEB_FRAIL, applier=self)

    def _curl_and_grow(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        BlockCmd.apply(ctx.hooks, self, _CURL_BLOCK)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _GROW_STR)

    def _pounce(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _POUNCE_DMG, 1)


LOUSE_PROGENITOR_NORMAL = Encounter(
    id="louse_progenitor_normal",
    monster_classes=[LouseProgenitor],
)
