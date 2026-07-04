"""Thieving Hopper (Hive). Sources: ThievingHopper.cs, ThievingHopperWeak.cs.

The stolen card is removed from the combat piles for good — in the game it
comes back as a post-combat reward when the hopper is killed, but the sim has
no out-of-combat rewards (see SwipePower).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...cards import Card
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_THEFT_DMG = 17
_HAT_TRICK_DMG = 21
_NAB_DMG = 14
_FLUTTER = 5
_ESCAPE_TIMER = 5


class ThievingHopper(MachineMonster):
    """THIEVERY (steal a card + 17) → FLUTTER (Flutter 5: half damage until
    5 unblocked hits land) → HAT_TRICK (21) → NAB (14) → ESCAPE. Spawns with
    the Escape Artist countdown."""

    min_hp = 79
    max_hp = 79

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_hovering = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import EscapeArtistPower
        PowerCmd.apply(hooks, self, EscapeArtistPower, _ESCAPE_TIMER)

    def build_machine(self) -> MonsterMoveStateMachine:
        thievery = MoveState(
            "THIEVERY_MOVE", self._thievery,
            Intent(MoveType.ATTACK, damage=_THEFT_DMG, also=(MoveType.CARD_DEBUFF,)),
        )
        flutter = MoveState("FLUTTER_MOVE", self._flutter, Intent(MoveType.BUFF))
        hat_trick = MoveState(
            "HAT_TRICK_MOVE", self._hat_trick,
            Intent(MoveType.ATTACK, damage=_HAT_TRICK_DMG),
        )
        nab = MoveState(
            "NAB_MOVE", self._nab, Intent(MoveType.ATTACK, damage=_NAB_DMG)
        )
        escape = MoveState("ESCAPE_MOVE", self._escape, Intent(MoveType.ESCAPE))
        thievery.follow_up = flutter
        flutter.follow_up = hat_trick
        hat_trick.follow_up = nab
        nab.follow_up = escape
        escape.follow_up = escape
        return MonsterMoveStateMachine(
            [thievery, nab, hat_trick, flutter, escape], thievery
        )

    @staticmethod
    def _steal_priorities():
        from ...cards import CardRarity
        return (
            lambda c: c.rarity == CardRarity.UNCOMMON,
            lambda c: c.rarity in (CardRarity.COMMON, CardRarity.RARE),
            lambda c: c.rarity == CardRarity.BASIC,
            lambda c: c.rarity == CardRarity.ANCIENT,
        )

    def _thievery(self, ctx: CombatCtx) -> None:
        player = ctx.player
        candidates: list[Card] = list(player.draw_pile) + list(player.discard_pile)
        for predicate in self._steal_priorities():
            subset = [c for c in candidates if predicate(c)]
            if subset:
                candidates = subset
                break
        if candidates:
            card = ctx.combat._rng.choice(candidates)
            for pile in (player.draw_pile, player.discard_pile):
                if card in pile:
                    pile.remove(card)
                    break
            # The card leaves the combat entirely (RemoveFromCombat).
            try:
                ctx.hooks.unregister(card)
            except ValueError:
                pass
            from ...cmds import PowerCmd
            from ...powers import SwipePower
            PowerCmd.apply(ctx.hooks, self, SwipePower, 1)
            self.powers["swipe"].stolen_cards.append(card)
        self._execute_attack(ctx, _THEFT_DMG, 1)

    def _flutter(self, ctx: CombatCtx) -> None:
        self.is_hovering = True
        from ...cmds import PowerCmd
        from ...powers import FlutterPower
        PowerCmd.apply(ctx.hooks, self, FlutterPower, _FLUTTER)

    def _hat_trick(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HAT_TRICK_DMG, 1)

    def _nab(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _NAB_DMG, 1)

    def _escape(self, ctx: CombatCtx) -> None:
        self.is_hovering = False
        from ...cmds import CreatureCmd
        CreatureCmd.escape(ctx.hooks, self)


THIEVING_HOPPER_WEAK = Encounter(
    id="thieving_hopper_weak",
    monster_classes=[ThievingHopper],
)
