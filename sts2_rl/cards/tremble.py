from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TrembleCard(Card):
    """Skill (Common, 1E) — apply 3 Vulnerable. Exhaust.

    Source: Tremble.cs
      Cost 1 | Skill | Common | TargetType.AnyEnemy | Exhaust
      OnUpgrade: Vulnerable +1 (→ 4)
    """
    id = "tremble"
    name = "Tremble"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._vulnerable = 3

    def _on_upgrade(self) -> None:
        self._vulnerable += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        if not target.is_gone:
            PowerCmd.apply(ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player)
