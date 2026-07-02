from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DarkEmbraceCard(Card):
    """Power (Rare, 2E) — whenever a card is exhausted, draw 1 card.

    Source: DarkEmbrace.cs
      Cost 2 | Power | Rare | TargetType.Self → DarkEmbracePower 1
      OnUpgrade: cost -1 (→ 1)
    """
    id = "dark_embrace"
    name = "Dark Embrace"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import DarkEmbracePower
        PowerCmd.apply(ctx.hooks, ctx.player, DarkEmbracePower, 1, applier=ctx.player)
