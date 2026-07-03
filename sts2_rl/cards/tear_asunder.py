from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TearAsunderCard(Card):
    """Attack (Rare, 2E) — deal 5 damage 1 time, plus 1 time for each time you
    lost HP this combat.

    Source: TearAsunder.cs
      Cost 2 | Attack | Rare | TargetType.AnyEnemy
      OnPlay: hitCount = 1 + count of DamageReceivedEntry with
        UnblockedDamage > 0 for the owner (whole combat); attack 5 × hitCount
      OnUpgrade: damage +2 (→ 7 per hit)
    """
    id = "tear_asunder"
    name = "Tear Asunder"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 5

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        hits = 1 + ctx.combat.history.times_damaged(ctx.player)
        for _ in range(hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
