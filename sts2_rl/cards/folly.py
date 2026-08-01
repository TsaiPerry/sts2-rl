from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FollyCard(Card):
    """Curse — Unplayable, Eternal, Innate, Ethereal.

    Source: Folly.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Unplayable, Eternal, Innate, Ethereal
      CanBeGeneratedByModifiers = false
    """
    id = "folly"
    name = "Folly"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    is_ethereal = True
    innate = True
    eternal = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
