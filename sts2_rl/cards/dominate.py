from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DominateCard(Card):
    """Skill (Uncommon, 1E) — apply 1 Vulnerable; gain Strength equal to the
    target's Vulnerable. Exhaust.

    Source: Dominate.cs
      Cost 1 | Skill | Uncommon | TargetType.AnyEnemy | Exhaust
      OnPlay: Vulnerable 1 to target, then Strength (self) = target's total
      Vulnerable after the application.
      OnUpgrade: Vulnerable +1 (→ 2)
    """
    id = "dominate"
    name = "Dominate"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._vulnerable = 1

    def _on_upgrade(self) -> None:
        self._vulnerable += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd, StrengthCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player)
        vuln = target.powers["vulnerable"].amount if "vulnerable" in target.powers else 0
        if vuln > 0:
            StrengthCmd.apply(ctx.hooks, ctx.player, vuln, card=self)
