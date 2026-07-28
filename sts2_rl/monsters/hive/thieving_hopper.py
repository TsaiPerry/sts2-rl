"""Thieving Hopper (Hive). Sources: ThievingHopper.cs, ThievingHopperWeak.cs.

The steal (SwipePower.cs Steal) removes the card from the run deck for good.
Killing the hopper queues the stolen card's deck version as a take-or-skip
post-combat reward (SwipePower.BeforeDeath -> CombatRoom.AddExtraReward with
a SpecialCardReward); if the hopper escapes, BeforeDeath never runs and the
card stays lost. See SwipePower.on_death and RunState.finish_combat.
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
    name = "Thieving Hopper"

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
        """ThievingHopper.cs:31-69 — the four `_stealPriorities` predicates, in
        order. The first three all require the card NOT to be Imbued; the
        fourth is the only tier an Imbued card can land in."""
        from ...cards import CardRarity
        from ...enchantments import ImbuedEnchantment

        def imbued(c) -> bool:
            return isinstance(c.enchantment, ImbuedEnchantment)

        return (
            lambda c: not imbued(c) and c.rarity == CardRarity.UNCOMMON,
            lambda c: not imbued(c) and c.rarity in (
                CardRarity.COMMON, CardRarity.RARE, CardRarity.EVENT),
            lambda c: not imbued(c) and c.rarity in (
                CardRarity.BASIC, CardRarity.QUEST),
            lambda c: c.rarity == CardRarity.ANCIENT or imbued(c),
        )

    def _thievery(self, ctx: CombatCtx) -> None:
        player = ctx.player
        candidates: list[Card] = list(player.draw_pile) + list(player.discard_pile)
        # Only real deck cards can be stolen (ThieveryMove filters the piles
        # on c.DeckVersion != null — combat-created cards like Slimed are
        # never taken). Standalone combats have no deck (origins empty), so
        # the filter only applies to run-backed combats.
        origins = ctx.combat.deck_card_origins
        if origins:
            candidates = [c for c in candidates if id(c) in origins]
        for predicate in self._steal_priorities():
            subset = [c for c in candidates if predicate(c)]
            if subset:
                candidates = subset
                break
        if candidates:
            # ThievingHopper.cs:222 —
            # base.RunRng.CombatCardGeneration.NextItem(enumerable).
            card = ctx.combat.combat_rng.card_gen.choice(candidates)
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
