from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class UnmovableCard(Card):
    """Power (Rare, 2E) — the first card that gains you block each turn grants
    double block.

    Source: Unmovable.cs
      Cost 2 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<UnmovablePower>(1)
      OnUpgrade: cost -1 (→ 1)
    """
    id = "unmovable"
    name = "Unmovable"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import UnmovablePower
        PowerCmd.apply(ctx.hooks, ctx.player, UnmovablePower, 1, applier=ctx.player)
