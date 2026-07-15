from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_VOMIT_SLIME = 10
_PUMMELING_DMG = 4
_PUMMELING_HITS = 4
_LEECHING_WEAK = 3
_LEECHING_STR = 3
_SMOTHER_DMG = 30


class SlimedBerserker(MachineMonster):
    """Vomit Ichor (10 Slimed) → Furious Pummeling (4×4) → Leeching Hug (Weak 3
    + gain 3 Strength) → Smother (30) → loop.

    Source: SlimedBerserker.cs (non-ascension values)."""

    min_hp = 261
    max_hp = 261

    def build_machine(self) -> MonsterMoveStateMachine:
        vomit = MoveState(
            "VOMIT_ICHOR_MOVE", self._vomit, Intent(MoveType.STATUS_CARD)
        )
        pummeling = MoveState(
            "FURIOUS_PUMMELING_MOVE", self._pummeling,
            Intent(MoveType.ATTACK, damage=_PUMMELING_DMG, hits=_PUMMELING_HITS),
        )
        leeching = MoveState(
            "LEECHING_HUG_MOVE", self._leeching,
            Intent(MoveType.DEBUFF, also=(MoveType.BUFF,)),
        )
        smother = MoveState(
            "SMOTHER_MOVE", self._smother,
            Intent(MoveType.ATTACK, damage=_SMOTHER_DMG),
        )
        vomit.follow_up = pummeling
        pummeling.follow_up = leeching
        leeching.follow_up = smother
        smother.follow_up = vomit
        return MonsterMoveStateMachine([vomit, smother, leeching, pummeling], vomit)

    def _vomit(self, ctx: CombatCtx) -> None:
        from ...cards import SlimedCard
        from ...cmds import CardPileCmd
        for _ in range(_VOMIT_SLIME):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())

    def _pummeling(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PUMMELING_DMG, _PUMMELING_HITS)

    def _leeching(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _LEECHING_WEAK)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _LEECHING_STR)

    def _smother(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SMOTHER_DMG, 1)


SLIMED_BERSERKER_NORMAL = Encounter(
    id="slimed_berserker_normal",
    monster_classes=[SlimedBerserker],
)
