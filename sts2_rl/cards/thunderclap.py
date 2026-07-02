from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ThunderclapCard(Card):
    """Attack (Common, 1E) — deal 4 damage to ALL enemies; apply 1 Vulnerable to ALL enemies.

    Source: Thunderclap.cs
      Cost 1 | Attack | Common | TargetType.AllEnemies
      OnPlay: attack all opponents, then Vulnerable 1 to every hittable enemy
      OnUpgrade: damage +3 (→ 7)

    handles_own_routing: all damage resolves before any Vulnerable is applied,
    mirroring the source's two passes.
    """
    id = "thunderclap"
    name = "Thunderclap"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ALL_ENEMIES
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 4
        self._vulnerable = 1

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower
        for enemy in list(ctx.enemies):
            if enemy.is_gone or ctx.player.is_dead:
                continue
            DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
        if ctx.player.is_dead:
            return
        for enemy in list(ctx.enemies):
            if not enemy.is_gone:
                PowerCmd.apply(ctx.hooks, enemy, VulnerablePower, self._vulnerable, applier=ctx.player)
