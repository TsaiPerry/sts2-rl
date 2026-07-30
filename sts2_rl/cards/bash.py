from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BashCard(Card):
    """Attack (Basic, 2E) — deal 8 damage and apply 2 Vulnerable.

    Source: Bash.cs
      Cost 2 | Attack | Basic | TargetType.AnyEnemy
      OnPlay: DamageCmd.Attack(8), then Vulnerable 2
      OnUpgrade: damage +2 (→ 10), Vulnerable +1 (→ 3)
    """
    id = "bash"
    name = "Bash"
    card_type = CardType.ATTACK
    rarity = CardRarity.BASIC
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 8
        self._vulnerable = 2

    def _on_upgrade(self) -> None:
        self._damage += 2
        self._vulnerable += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        # No liveness guard: C# applies this unconditionally and the only
        # gate is `Creature.CanReceivePowers` (Creature.cs:308-322), now
        # enforced inside PowerCmd.apply.
        PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player)
