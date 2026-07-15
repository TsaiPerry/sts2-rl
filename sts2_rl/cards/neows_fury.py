from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class NeowsFuryCard(Card):
    """Attack (Ancient, 1E) — deal 10 damage; return up to 2 chosen cards from
    your discard pile to your hand. Exhaust.

    Source: NeowsFury.cs
      Cost 1 | Attack | Ancient | TargetType.AnyEnemy | Exhaust
      CanBeGeneratedInCombat = false (only Neow's Torment grants it)
      OnPlay: attack 10 → FromCombatPile(discard, 0..2) → add to hand,
        capped at MaxCardsInHand
      OnUpgrade: damage +4 (→ 14), cards +1 (→ 3)
    """

    id = "neows_fury"
    name = "Neow's Fury"
    card_type = CardType.ATTACK
    rarity = CardRarity.ANCIENT
    target_type = TargetType.ANY_ENEMY
    # CanBeGeneratedInCombat=false in the source; the Ancient rarity already
    # keeps it out of the sim's combat-generation pool (pool_card_ids).
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 10
        self._cards = 2

    def _on_upgrade(self) -> None:
        self._damage += 4
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DamageCmd
        from ..player import PlayerCombatState

        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        room = PlayerCombatState.MAX_HAND_SIZE - len(ctx.player.hand)
        count = min(self._cards, room)
        if count <= 0:
            return
        chosen = CardSelectCmd.from_pile(
            ctx.hooks, ctx.player.discard_pile, "from_discard",
            count=count, predicate=lambda c: c is not self,
        )
        for card in chosen:
            ctx.player.discard_pile.remove(card)
            ctx.player.hand.append(card)
