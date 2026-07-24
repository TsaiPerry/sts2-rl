from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_HAUNT_WEAK = 3
_HAUNT_DAZED = 5
_SWIPE_DMG = 13
_STOMP_DMG = 4
_STOMP_HITS = 3


class HauntedShip(MachineMonster):
    """Opens with HAUNT (Weak 3 + 5 Dazed into the discard pile), then
    alternates SWIPE and STOMP forever."""
    name = "Haunted Ship"

    min_hp = 63
    max_hp = 63

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        swipe = MoveState(
            "SWIPE_MOVE", self._swipe, Intent(MoveType.ATTACK, damage=_SWIPE_DMG)
        )
        stomp = MoveState(
            "STOMP_MOVE", self._stomp,
            Intent(MoveType.ATTACK, damage=_STOMP_DMG, hits=_STOMP_HITS),
        )
        haunt = MoveState(
            "HAUNT_MOVE", self._haunt,
            Intent(MoveType.DEBUFF, also=(MoveType.STATUS_CARD,)),
        )
        haunt.follow_up = swipe
        swipe.follow_up = stomp
        stomp.follow_up = swipe
        return MonsterMoveStateMachine([swipe, stomp, haunt], haunt)

    def _swipe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SWIPE_DMG, 1)

    def _stomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STOMP_DMG, _STOMP_HITS)

    def _haunt(self, ctx: CombatCtx) -> None:
        from ...cards import DazedCard
        from ...cmds import CardPileCmd, PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _HAUNT_WEAK)
        for _ in range(_HAUNT_DAZED):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, DazedCard())


HAUNTED_SHIP_NORMAL = Encounter(
    id="haunted_ship_normal",
    monster_classes=[HauntedShip],
)
