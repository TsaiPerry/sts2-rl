from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class UnrelentingCard(Card):
    """Attack (Uncommon, 2E) — deal 14 damage; your next Attack costs 0.

    Source: Unrelenting.cs
      Cost 2 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: DamageCmd.Attack(14), then PowerCmd.Apply<FreeAttackPower>(1)
      OnUpgrade: damage +6 (→ 20)
    """
    id = "unrelenting"
    name = "Unrelenting"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 14

    def _on_upgrade(self) -> None:
        self._damage += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import FreeAttackPower
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        PowerCmd.apply(ctx.hooks, ctx.player, FreeAttackPower, 1, applier=ctx.player)
