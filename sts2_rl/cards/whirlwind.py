from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class WhirlwindCard(Card):
    """Attack (Uncommon, X) — deal 5 damage to ALL enemies X times.

    Source: Whirlwind.cs
      Cost X | Attack | Uncommon | TargetType.AllEnemies
      OnPlay: attack 5 with hit count = ResolveEnergyXValue() targeting all
        opponents
      OnUpgrade: damage +3 (→ 8 per hit)

    handles_own_routing: each hit sweeps every living enemy (like
    Conflagration), so the card iterates hits × enemies itself.
    """
    id = "whirlwind"
    name = "Whirlwind"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ALL_ENEMIES
    energy_cost_x = True
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 5

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        for _ in range(self.captured_x):
            living = [e for e in ctx.enemies if not e.is_gone]
            if not living or ctx.player.is_dead:
                return
            for enemy in living:
                if not enemy.is_gone:
                    DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
                    if ctx.player.is_dead:
                        return
