from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class UppercutCard(Card):
    """Attack (Uncommon, 2E) — deal 13 damage; apply 1 Weak and 1 Vulnerable.

    Source: Uppercut.cs
      Cost 2 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: Attack(13), then Weak 1 and Vulnerable 1
      OnUpgrade: Weak/Vulnerable +1 each (→ 2/2); damage unchanged
    """
    id = "uppercut"
    name = "Uppercut"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 13
        self._power = 1

    def _on_upgrade(self) -> None:
        self._power += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower, WeakPower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        # No liveness guard: C# applies this unconditionally and the only
        # gate is `Creature.CanReceivePowers` (Creature.cs:308-322), now
        # enforced inside PowerCmd.apply.
        PowerCmd.apply(ctx.hooks, target, WeakPower, self._power, applier=ctx.player)
        PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._power, applier=ctx.player)
