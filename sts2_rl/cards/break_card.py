from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BreakCard(Card):
    """Attack (Ancient, 1E) — deal 20 damage and apply 5 Vulnerable.

    Source: Break.cs
      Cost 1 | Attack | Ancient | TargetType.AnyEnemy
      OnUpgrade: damage +10 (→ 30), Vulnerable +2 (→ 7)
    """
    id = "break"
    name = "Break"
    card_type = CardType.ATTACK
    rarity = CardRarity.ANCIENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 20
        self._vulnerable = 5

    def _on_upgrade(self) -> None:
        self._damage += 10
        self._vulnerable += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if not target.is_gone:
            PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player)
