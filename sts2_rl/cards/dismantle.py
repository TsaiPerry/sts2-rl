from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DismantleCard(Card):
    """Attack (Uncommon, 1E) — deal 8 damage; twice if the target is Vulnerable.

    Source: Dismantle.cs
      Cost 1 | Attack | Uncommon | TargetType.AnyEnemy
      hitCount = target has Vulnerable ? 2 : 1 (checked before the first hit)
      OnUpgrade: damage +2 (→ 10)
    """
    id = "dismantle"
    name = "Dismantle"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 8

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        hits = 2 if "vulnerable" in target.powers else 1
        for _ in range(hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)

    def _should_glow_gold_internal(self, ctx) -> bool:
        # Dismantle.cs:18: CombatState?.HittableEnemies.Any(e =>
        # e.HasPower<VulnerablePower>()) ?? false
        return any("vulnerable" in e.powers for e in ctx.hittable_enemies)
