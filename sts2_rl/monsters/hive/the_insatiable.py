"""The Insatiable (Hive boss). Sources: TheInsatiable.cs,
TheInsatiableBoss.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx

_THRASH_DMG = 8
_THRASH_HITS = 2
_BITE_DMG = 28
_SALIVATE_STR = 2
_SANDPIT = 4
_ESCAPE_DRAW = 3
_ESCAPE_DISCARD = 3


class TheInsatiable(MachineMonster):
    """Opens with LIQUIFY_GROUND: Sandpit 4 (a devour timer — when it runs out
    the player is eaten alive) and 6 Frantic Escape statuses (3 in the draw
    pile, 3 in the discard; playing one buys a turn). Then loops THRASH (8x2)
    → LUNGING_BITE (28) → SALIVATE (+2 Strength) → THRASH_2 (8x2) → THRASH."""

    min_hp = 321
    max_hp = 321

    def build_machine(self) -> MonsterMoveStateMachine:
        liquify = MoveState(
            "LIQUIFY_GROUND_MOVE", self._liquify,
            Intent(MoveType.BUFF, also=(MoveType.STATUS_CARD,)),
        )
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            Intent(MoveType.ATTACK, damage=_THRASH_DMG, hits=_THRASH_HITS),
        )
        thrash2 = MoveState(
            "THRASH_MOVE_2", self._thrash,
            Intent(MoveType.ATTACK, damage=_THRASH_DMG, hits=_THRASH_HITS),
        )
        bite = MoveState(
            "LUNGING_BITE_MOVE", self._bite,
            Intent(MoveType.ATTACK, damage=_BITE_DMG),
        )
        salivate = MoveState("SALIVATE_MOVE", self._salivate, Intent(MoveType.BUFF))
        liquify.follow_up = thrash
        thrash.follow_up = bite
        bite.follow_up = salivate
        salivate.follow_up = thrash2
        thrash2.follow_up = thrash
        return MonsterMoveStateMachine(
            [liquify, bite, thrash, thrash2, salivate], liquify
        )

    def _liquify(self, ctx: CombatCtx) -> None:
        from ...cards import FranticEscapeCard
        from ...cmds import CardPileCmd, PowerCmd
        from ...powers import SandpitPower
        PowerCmd.apply(ctx.hooks, self, SandpitPower, _SANDPIT)
        for _ in range(_ESCAPE_DRAW):
            CardPileCmd.add_to_draw(ctx.hooks, ctx.player, FranticEscapeCard())
        for _ in range(_ESCAPE_DISCARD):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, FranticEscapeCard())

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _THRASH_DMG, _THRASH_HITS)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _salivate(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _SALIVATE_STR)


THE_INSATIABLE_BOSS = Encounter(
    id="the_insatiable_boss",
    monster_classes=[TheInsatiable],
)
