from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SlimedCard(Card):
    """Status (1E) — Exhaust; draw 1 card.

    Source: Slimed.cs
      Cost 1 | Status | Status | TargetType.None | CardsVar(1)
      Keywords: Exhaust (playable, unlike most statuses)
      OnPlay: CardPileCmd.Draw(1)
    """
    id = "slimed"
    name = "Slimed"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    exhausts = True
    max_upgrade_level = 0

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd
        DrawCmd.draw(ctx.player, 1)
