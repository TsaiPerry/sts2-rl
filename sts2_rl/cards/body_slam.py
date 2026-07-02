from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class BodySlamCard(Card):
    """Attack (Common, 1E) — deal damage equal to your current block.

    Source: BodySlam.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy
      CalculationBase 0, ExtraDamage 1, multiplier = owner's block
      OnUpgrade: cost -1 (→ 0)
    """
    id = "body_slam"
    name = "Body Slam"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def calc_damage(self, ctx: CombatCtx, target: Creature | None = None) -> int:
        return ctx.player.block

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self.calc_damage(ctx, target), dealer=ctx.player, card=self)
