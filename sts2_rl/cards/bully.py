from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class BullyCard(Card):
    """Attack (Uncommon, 0E) — deal 4 + 2 damage per Vulnerable on the target.

    Source: Bully.cs
      Cost 0 | Attack | Uncommon | TargetType.AnyEnemy
      CalculationBase 4, ExtraDamage 2, multiplier = target's Vulnerable amount
      OnUpgrade: extra damage +1 (→ 4 + 3×vuln)
    """
    id = "bully"
    name = "Bully"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._base = 4
        self._extra = 2

    def _on_upgrade(self) -> None:
        self._extra += 1

    def calc_damage(self, ctx: CombatCtx, target: Creature | None = None) -> int:
        vuln = target.powers["vulnerable"].amount if target is not None and "vulnerable" in target.powers else 0
        return self._base + self._extra * vuln

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self.calc_damage(ctx, target), dealer=ctx.player, card=self)
