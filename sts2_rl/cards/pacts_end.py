from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PactsEndCard(Card):
    """Attack (Rare, 0E) — if you have 3+ cards in the exhaust pile, deal 17 damage to ALL enemies.

    Source: PactsEnd.cs
      Cost 0 | Attack | Rare | TargetType.AllEnemies
      CanDealDamage = exhaust pile count >= 3; otherwise the play does nothing
      OnUpgrade: damage +6 (→ 23)
    """
    id = "pacts_end"
    name = "Pact's End"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 17
        self._required_exhausted = 3

    def _on_upgrade(self) -> None:
        self._damage += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        if len(ctx.player.exhaust_pile) < self._required_exhausted:
            return
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
