from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BarricadeCard(Card):
    """Power (Rare, 3E) — block is not removed at the start of your turn.

    Source: Barricade.cs
      Cost 3 | Power | Rare | TargetType.Self → BarricadePower 1
      OnUpgrade: cost -1 (→ 2)
    """
    id = "barricade"
    name = "Barricade"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import BarricadePower
        PowerCmd.apply(ctx.hooks, ctx.player, BarricadePower, 1, applier=ctx.player)
