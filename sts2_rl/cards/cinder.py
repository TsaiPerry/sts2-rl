from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class CinderCard(Card):
    """Attack (Common, 2E) — deal 18 damage; exhaust a random card from your hand.

    Source: Cinder.cs
      Cost 2 | Attack | Common | TargetType.AnyEnemy
      OnPlay: DamageCmd.Attack(18), then exhaust a random hand card
      OnUpgrade: damage +6 (→ 24)
    """
    id = "cinder"
    name = "Cinder"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 18

    def _on_upgrade(self) -> None:
        self._damage += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, ExhaustCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
        if ctx.player.hand:
            victim = ctx.combat._rng.choice(ctx.player.hand)
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, victim)
