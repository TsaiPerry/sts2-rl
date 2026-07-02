from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class GiantRockCard(Card):
    """Attack (Token, 1E) — deal 16 damage. Created by Primal Force.

    Source: GiantRock.cs
      Cost 1 | Attack | Token | TargetType.AnyEnemy
      OnUpgrade: damage +4 (→ 20)
    """
    id = "giant_rock"
    name = "Giant Rock"
    card_type = CardType.ATTACK
    rarity = CardRarity.TOKEN
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 16

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
