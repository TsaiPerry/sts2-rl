from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ConflagrationCard(Card):
    """Attack (Rare, 1E) — deal 2 damage to ALL enemies 4 times.

    Source: Conflagration.cs
      Cost 1 | Attack | Rare | TargetType.AllEnemies
      Damage 2, Repeat 4 (WithHitCount targeting all opponents)
      OnUpgrade: repeat +1 (→ 5)

    handles_own_routing: each hit sweeps every living enemy, so the card
    iterates hits × enemies itself.
    """
    id = "conflagration"
    name = "Conflagration"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ALL_ENEMIES
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 2
        self._hits = 4

    def _on_upgrade(self) -> None:
        self._hits += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        for _ in range(self._hits):
            living = [e for e in ctx.enemies if not e.is_gone]
            if not living or ctx.player.is_dead:
                return
            for enemy in living:
                if not enemy.is_gone:
                    DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
                    if ctx.player.is_dead:
                        return
