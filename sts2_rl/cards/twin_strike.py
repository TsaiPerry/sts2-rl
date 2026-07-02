from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TwinStrikeCard(Card):
    """Attack (Common, 1E) — deal 5 damage twice.

    Source: TwinStrike.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy | Strike tag
      OnUpgrade: damage +2 (→ 7 per hit)
    """
    id = "twin_strike"
    name = "Twin Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 5
        self._hits = 2

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
