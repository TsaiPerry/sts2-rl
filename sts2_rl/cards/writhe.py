from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class WritheCard(Card):
    """Curse — Unplayable, Innate.

    Source: Writhe.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Innate, Unplayable
    """
    id = "writhe"
    name = "Writhe"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    innate = True
    max_upgrade_level = 0
    is_unpowered = True

    def _init_vars(self) -> None:
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
