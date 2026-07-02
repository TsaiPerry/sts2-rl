from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ImperviousCard(Card):
    """Skill (Rare, 2E) — gain 30 block. Exhaust.

    Source: Impervious.cs
      Cost 2 | Skill | Rare | TargetType.Self | Exhaust
      OnUpgrade: block +10 (→ 40)
    """
    id = "impervious"
    name = "Impervious"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._block = 30

    def _on_upgrade(self) -> None:
        self._block += 10

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
