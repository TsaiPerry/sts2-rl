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
    name = "The Insatiable"

    min_hp = 321
    max_hp = 321

    def build_machine(self) -> MonsterMoveStateMachine:
        liquify = MoveState(
            "LIQUIFY_GROUND_MOVE", self._liquify,
            # TheInsatiable.cs:96 `new StatusIntent(6)` -- a bare literal, not
            # derived from _ESCAPE_DRAW/_ESCAPE_DISCARD below (which happen to
            # sum to it): the C# telegraph count and the move's mechanical
            # effect are two independent reads of the same design number.
            Intent(MoveType.BUFF, also=(MoveType.STATUS_CARD,), status_count=6),
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
            self._add_escape_to_discard(ctx)

    @staticmethod
    def _add_escape_to_discard(ctx: CombatCtx) -> None:
        """LiquifyGroundMove passes CardPilePosition.Random for the DISCARDED
        half too (TheInsatiable.cs:130-137 — one loop over i in [0, 6), the
        pile type is the only thing that changes at i == 3), and
        CardPileCmd.cs:512-514 resolves Random to
        ``Rng.Shuffle.NextInt(Cards.Count + 1)`` for every pile type. So each
        of these three takes a draw and lands at a random slot, exactly like
        the draw-pile half; CardPileCmd.add_to_discard has no position argument
        yet and appends, so the placement is inlined here against the same
        primitive add_to_draw uses. Unlike the draw pile, the sim's discard
        shares the game's orientation (index 0 = top, append = bottom), so the
        game index is used unchanged."""
        from ...cards import FranticEscapeCard
        from ...cmds import CardPileCmd
        card = FranticEscapeCard()
        crng = ctx.combat.combat_rng
        count = len(ctx.player.discard_pile)
        if crng.is_parity:
            ctx.player.discard_pile.insert(crng.shuffle.randrange(count + 1), card)
        else:
            ctx.player.discard_pile.insert(
                ctx.combat._rng.randrange(count + 1), card)
        CardPileCmd._enter_combat(ctx.hooks, card)

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
