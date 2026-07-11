from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DefendCard(Card):
    id = "defend"
    name = "Defend"
    card_type = CardType.SKILL
    rarity = CardRarity.BASIC
    target_type = TargetType.SELF
    tags = frozenset({"defend"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 5

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
