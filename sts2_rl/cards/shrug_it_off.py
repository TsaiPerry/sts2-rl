from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ShrugItOffCard(Card):
    """Skill (Common, 1E) — gain 8 block; draw 1 card.

    Source: ShrugItOff.cs
      Cost 1 | Skill | Common | TargetType.Self
      OnUpgrade: block +3 (→ 11)
    """
    id = "shrug_it_off"
    gains_block = True  # CardModel.GainsBlock
    name = "Shrug It Off"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 8
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, DrawCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        DrawCmd.draw(ctx.player, self._cards)
