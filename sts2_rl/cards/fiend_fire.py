from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FiendFireCard(Card):
    """Attack (Rare, 2E) — exhaust your hand; deal 7 damage per card exhausted. Exhaust.

    Source: FiendFire.cs
      Cost 2 | Attack | Rare | TargetType.AnyEnemy | Exhaust
      OnPlay: count hand, exhaust every card in it, then hit count times
      OnUpgrade: damage +3 (→ 10)
    """
    id = "fiend_fire"
    name = "Fiend Fire"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 7

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, ExhaustCmd
        target = ctx.resolve_target(target_idx)
        hand = list(ctx.player.hand)
        for card in hand:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)
        for _ in range(len(hand)):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
