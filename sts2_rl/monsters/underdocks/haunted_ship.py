from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_HAUNT_WEAK = 3
_HAUNT_DAZED = 5
_SWIPE_DMG = 13              # HauntedShip.cs:31 base
_SWIPE_DMG_ASC = 14          # DeadlyEnemies (asc 9+)
_STOMP_DMG = 4               # HauntedShip.cs:33 base
_STOMP_DMG_ASC = 5           # DeadlyEnemies (asc 9+)
_STOMP_HITS = 3


class HauntedShip(MachineMonster):
    """Opens with HAUNT (Weak 3 + 5 Dazed into the discard pile), then
    alternates SWIPE and STOMP forever."""
    name = "Haunted Ship"

    min_hp = 63          # HauntedShip.cs:25 base (MaxInitialHp == MinInitialHp)
    max_hp = 63
    min_hp_asc = 67       # ToughEnemies (asc 8+)
    max_hp_asc = 67

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _swipe_dmg(self) -> int:
        """HauntedShip.cs:31 `SwipeDamage` -- re-read at both the telegraphed
        Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SWIPE_DMG_ASC, _SWIPE_DMG)

    def _stomp_dmg(self) -> int:
        """HauntedShip.cs:33 `StompDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _STOMP_DMG_ASC, _STOMP_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        swipe = MoveState(
            "SWIPE_MOVE", self._swipe,
            lambda: Intent(MoveType.ATTACK, damage=self._swipe_dmg()),
        )
        stomp = MoveState(
            "STOMP_MOVE", self._stomp,
            lambda: Intent(MoveType.ATTACK, damage=self._stomp_dmg(), hits=_STOMP_HITS),
        )
        haunt = MoveState(
            "HAUNT_MOVE", self._haunt,
            Intent(MoveType.DEBUFF, also=(MoveType.STATUS_CARD,),
                   status_count=_HAUNT_DAZED),
        )
        haunt.follow_up = swipe
        swipe.follow_up = stomp
        stomp.follow_up = swipe
        return MonsterMoveStateMachine([swipe, stomp, haunt], haunt)

    def _swipe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._swipe_dmg(), 1)

    def _stomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._stomp_dmg(), _STOMP_HITS)

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
