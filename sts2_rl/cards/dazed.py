from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DazedCard(Card):
    """Status — Unplayable, Ethereal.

    Source: Dazed.cs
      Cost -1 | Status | Status | TargetType.None
      Keywords: Ethereal, Unplayable; no effects
    """
    id = "dazed"
    name = "Dazed"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    is_ethereal = True
    max_upgrade_level = 0
    is_unpowered = True

    def _init_vars(self) -> None:
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
