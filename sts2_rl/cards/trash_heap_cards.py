"""The Trash Heap event's card-reward pool (Act 2 / Underdocks).

Source: TrashHeap.cs `Cards` — 10 off-colour Event-rarity cards, one rolled at
random when the player takes the Grab option: Caltrops, Clash, Distraction,
Dual Wield, Entrench, Hello World, Outmaneuver, Rebound, Rip and Tear, Stack.
Each is ported from its own card model (src/Core/Models/Cards).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import (
    Card, CardRarity, CardType, TargetType, create_clone, register_card,
)

if TYPE_CHECKING:
    from ..combat import CombatCtx


def _clone(card: Card) -> Card:
    """Duplicate a card the way CardModel.CreateClone does — same upgrade
    level, and carrying a live copy of the source's enchantment and affliction
    (Dual Wield's copies)."""
    return create_clone(card)


@register_card
class CaltropsCard(Card):
    """Power (Event, 1E) — gain 3 Thorns.

    Source: Caltrops.cs — ThornsPower 3, OnUpgrade +2.
    """
    id = "caltrops"
    name = "Caltrops"
    card_type = CardType.POWER
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 3

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import ThornsPower
        PowerCmd.apply(ctx.hooks, ctx.player, ThornsPower, self._power_amount, applier=ctx.player)


@register_card
class ClashCard(Card):
    """Attack (Event, 0E) — deal 14 damage. Can only be played if every card in
    your hand is an Attack.

    Source: Clash.cs — Damage 14 (Move), IsPlayable = all hand cards are
    Attacks, OnUpgrade +4.
    """
    id = "clash"
    name = "Clash"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 14

    def _on_upgrade(self) -> None:
        self._damage += 4

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        # IsPlayable gate: only playable while the hand is all Attacks (the
        # card is registered as a hook listener, so this vetoes its own play).
        if card is not self or self.combat is None:
            return True
        return all(c.card_type == CardType.ATTACK for c in self.combat.player.hand)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )


@register_card
class DistractionCard(Card):
    """Skill (Event, 1E, Exhaust) — add a random Skill to your hand; it costs 0
    this turn.

    Source: Distraction.cs — GetDistinctForCombat 1 Skill, free this turn,
    added to hand, OnUpgrade cost -1.
    """
    id = "distraction"
    name = "Distraction"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cards import CardType as _CT
        from ..cards.pool import random_pool_cards
        from ..cmds import CardPileCmd
        generated = random_pool_cards(ctx.combat._rng, 1, _CT.SKILL, distinct=True)
        for card in generated:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)


@register_card
class DualWieldCard(Card):
    """Skill (Event, 1E) — choose an Attack or Power in your hand; add a copy
    of it to your hand.

    Source: DualWield.cs — CardsVar 1, clone a chosen Attack/Power that many
    times into the hand, OnUpgrade +1.
    """
    id = "dual_wield"
    name = "Dual Wield"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardPileCmd, CardSelectCmd
        chosen = CardSelectCmd.from_hand(
            ctx.hooks, ctx.player, "duplicate", 1,
            predicate=lambda c: c.card_type in (CardType.ATTACK, CardType.POWER),
        )
        if not chosen:
            return
        for _ in range(self._cards):
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, _clone(chosen[0]))


@register_card
class EntrenchCard(Card):
    """Skill (Event, 2E) — double your current block.

    Source: Entrench.cs — GainBlock(current Block, Unpowered | Move),
    OnUpgrade cost -1.
    """
    id = "entrench"
    gains_block = True  # CardModel.GainsBlock
    name = "Entrench"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        from ..valueprops import ValueProp
        BlockCmd.apply(
            ctx.hooks, ctx.player, ctx.player.block,
            card=self, props=ValueProp.MOVE | ValueProp.UNPOWERED,
        )


@register_card
class HelloWorldCard(Card):
    """Power (Event, 1E) — at the start of each turn, add a random Common card
    to your hand.

    Source: HelloWorld.cs — HelloWorldPower 1, OnUpgrade Innate.
    """
    id = "hello_world"
    name = "Hello World"
    card_type = CardType.POWER
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self.innate = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import HelloWorldPower
        PowerCmd.apply(ctx.hooks, ctx.player, HelloWorldPower, 1, applier=ctx.player)


@register_card
class OutmaneuverCard(Card):
    """Skill (Event, 1E) — gain 2 energy next turn.

    Source: Outmaneuver.cs — EnergyNextTurnPower 2, OnUpgrade +1.
    """
    id = "outmaneuver"
    name = "Outmaneuver"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._energy = 2

    def _on_upgrade(self) -> None:
        self._energy += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import EnergyNextTurnPower
        PowerCmd.apply(ctx.hooks, ctx.player, EnergyNextTurnPower, self._energy, applier=ctx.player)


@register_card
class ReboundCard(Card):
    """Attack (Event, 1E) — deal 9 damage. The next card you play this turn goes
    on top of your draw pile.

    Source: Rebound.cs — Damage 9 (Move), then ReboundPower 1, OnUpgrade +3.
    """
    id = "rebound"
    name = "Rebound"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import ReboundPower
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        PowerCmd.apply(ctx.hooks, ctx.player, ReboundPower, 1, applier=ctx.player)


@register_card
class RipAndTearCard(Card):
    """Attack (Event, 1E) — deal 7 damage to a random enemy twice.

    Source: RipAndTear.cs — Damage 7 (Move), 2 hits, TargetingRandomOpponents,
    OnUpgrade +2.
    """
    id = "rip_and_tear"
    name = "Rip and Tear"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.RANDOM_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 7
        self._hits = 2

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        # AttackCommand.cs:601-602 (TargetingRandomOpponents): one
        # Rng.CombatTargets.NextItem(validTargets) per hit, re-rolled each
        # time. Parity routes to that stream; legacy keeps the shared
        # random.Random pick. Same shape as cards/sword_boomerang.py.
        crng = ctx.combat.combat_rng
        for _ in range(self._hits):
            living = [e for e in ctx.combat.enemies if not e.is_gone]
            if not living:
                break
            if crng.is_parity:
                target = crng.targets.choice(living)
            else:
                target = ctx.combat._rng.choice(living)
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)


@register_card
class StackCard(Card):
    """Skill (Event, 1E) — gain block equal to the number of cards in your
    discard pile.

    Source: Stack.cs — CalculatedBlock = CalculationExtra(1) × discard-pile
    count (+ CalculationBase 0), OnUpgrade base +3. The played Stack is not
    counted (it resolves out of the discard pile).
    """
    id = "stack"
    gains_block = True  # CardModel.GainsBlock
    name = "Stack"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 0  # CalculationBase

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        discard_count = sum(1 for c in ctx.player.discard_pile if c is not self)
        BlockCmd.apply(ctx.hooks, ctx.player, self._block + discard_count, card=self)
