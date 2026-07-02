from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class MangleCard(Card):
    """Attack (Rare, 3E) — deal 15 damage; the target loses 10 Strength until
    the end of its turn.

    Source: Mangle.cs
      Cost 3 | Attack | Rare | TargetType.AnyEnemy
      OnPlay: DamageCmd.Attack(15), then PowerCmd.Apply<ManglePower>(10)
        (ManglePower : TemporaryStrengthPower with IsPositive=false)
      OnUpgrade: damage +5 (→ 20), strength loss +5 (→ 15)
    """
    id = "mangle"
    name = "Mangle"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 15
        self._strength_loss = 10

    def _on_upgrade(self) -> None:
        self._damage += 5
        self._strength_loss += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import ManglePower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if not target.is_gone:
            PowerCmd.apply(
                ctx.hooks, target, ManglePower, self._strength_loss, applier=ctx.player
            )
