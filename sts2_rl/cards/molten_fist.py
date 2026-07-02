from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class MoltenFistCard(Card):
    """Attack (Common, 1E) — deal 10 damage; double the target's Vulnerable. Exhaust.

    Source: MoltenFist.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy | Exhaust
      OnPlay: Attack(10); then if target alive with N Vulnerable (N > 0),
      apply N more Vulnerable.
      OnUpgrade: damage +4 (→ 14)
    """
    id = "molten_fist"
    name = "Molten Fist"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 10

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if not target.is_gone and "vulnerable" in target.powers:
            vuln = target.powers["vulnerable"].amount
            if vuln > 0:
                PowerCmd.apply(ctx.hooks, target, VulnerablePower, vuln, applier=ctx.player)
