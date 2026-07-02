from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class RuptureCard(Card):
    """Power (Uncommon, 1E) — whenever you lose HP from damage, gain 1 Strength.

    Source: Rupture.cs
      Cost 1 | Power | Uncommon | TargetType.Self → RupturePower 1
      OnUpgrade: Strength per trigger +1 (→ 2)
    """
    id = "rupture"
    name = "Rupture"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._strength = 1

    def _on_upgrade(self) -> None:
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import RupturePower
        PowerCmd.apply(ctx.hooks, ctx.player, RupturePower, self._strength, applier=ctx.player)
