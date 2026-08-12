"""Louse Progenitor (Hive). Sources: LouseProgenitor.cs,
LouseProgenitorNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_WEB_DMG = 9                # LouseProgenitor.cs:61 base
_WEB_DMG_ASC = 10           # DeadlyEnemies (asc 9+)
_WEB_FRAIL = 2
_POUNCE_DMG = 14            # LouseProgenitor.cs:63 base
_POUNCE_DMG_ASC = 16        # DeadlyEnemies (asc 9+)
_CURL_BLOCK = 14            # LouseProgenitor.cs:65 base -- gated on ToughEnemies
_CURL_BLOCK_ASC = 18        # ToughEnemies (asc 8+)
_GROW_STR = 5


class LouseProgenitor(MachineMonster):
    """Spawns with Curl Up 14 (blocks when first hit). Cycle: WEB_CANNON
    (9 + Frail 2) → CURL_AND_GROW (14 block + 5 Strength) → POUNCE (14)."""
    name = "Louse Progenitor"

    min_hp = 134
    max_hp = 136
    min_hp_asc = 138     # LouseProgenitor.cs:38 ToughEnemies (asc 8+)
    max_hp_asc = 141     # LouseProgenitor.cs:40 ToughEnemies (asc 8+)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import CurlUpPower
        PowerCmd.apply(hooks, self, CurlUpPower, self._curl_block())

    def _web_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _WEB_DMG_ASC, _WEB_DMG)

    def _pounce_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _POUNCE_DMG_ASC, _POUNCE_DMG)

    def _curl_block(self) -> int:
        """LouseProgenitor.cs:65 `CurlBlock` -- read at the initial
        AfterAddedToRoom apply (:70) and the CURL_AND_GROW move (:106)."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _CURL_BLOCK_ASC, _CURL_BLOCK)

    def build_machine(self) -> MonsterMoveStateMachine:
        web = MoveState(
            "WEB_CANNON_MOVE", self._web,
            lambda: Intent(MoveType.ATTACK, damage=self._web_dmg(),
                            also=(MoveType.DEBUFF,)),
        )
        curl = MoveState(
            "CURL_AND_GROW_MOVE", self._curl_and_grow,
            Intent(MoveType.DEFEND, also=(MoveType.BUFF,)),
        )
        pounce = MoveState(
            "POUNCE_MOVE", self._pounce,
            lambda: Intent(MoveType.ATTACK, damage=self._pounce_dmg()),
        )
        web.follow_up = curl
        curl.follow_up = pounce
        pounce.follow_up = web
        return MonsterMoveStateMachine([curl, web, pounce], web)

    def _web(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._web_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _WEB_FRAIL, applier=self)

    def _curl_and_grow(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        BlockCmd.apply(ctx.hooks, self, self._curl_block())
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _GROW_STR)

    def _pounce(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._pounce_dmg(), 1)


LOUSE_PROGENITOR_NORMAL = Encounter(
    id="louse_progenitor_normal",
    monster_classes=[LouseProgenitor],
)
