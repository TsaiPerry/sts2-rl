from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BreakthroughCard(Card):
    """Attack (Common, 1E) — deal 1 unblockable HP loss to self, then 9 damage to ALL enemies.

    Source: Breakthrough.cs
      Cost 1 | Attack | Common | TargetType.AllEnemies
      OnPlay:
        CreatureCmd.Damage(self, 1, Unblockable | Unpowered | Move)   ← bypasses block, no Strength
        DamageCmd.Attack(9).TargetingAllOpponents                      ← scales with Strength
      OnUpgrade: damage +4 (→ 13)

    handles_own_routing = True because the self-damage must fire exactly once
    regardless of how many enemies are alive; the framework's per-enemy loop
    would call on_play multiple times and repeat the self-damage.
    """
    id = "breakthrough"
    name = "Breakthrough"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ALL_ENEMIES
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        # 1 unblockable HP loss to self (bypasses block; no Strength scaling).
        p = ctx.player
        old_hp = p.hp
        p.hp = max(0, p.hp - 1)
        hp_lost = old_hp - p.hp
        if hp_lost > 0:
            ctx.hooks.on_hp_changed(p, -hp_lost)
            if p.hp <= 0 and ctx.hooks.should_die(p):
                ctx.hooks.on_death(p)
        if ctx.player.is_dead:
            return
        # 9 (+ Strength) damage to each living enemy.
        for enemy in list(ctx.enemies):
            if not enemy.is_dead:
                DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
                if ctx.player.is_dead:
                    break
