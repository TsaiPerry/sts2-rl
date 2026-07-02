from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BludgeonCard(Card):
    """Attack (Uncommon, 3E) — deal 32 damage.

    Source: Bludgeon.cs
      Cost 3 | Attack | Uncommon | TargetType.AnyEnemy
      OnUpgrade: damage +10 (→ 42)
    """
    id = "bludgeon"
    name = "Bludgeon"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 32

    def _on_upgrade(self) -> None:
        self._damage += 10

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
