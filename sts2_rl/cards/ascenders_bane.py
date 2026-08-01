from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class AscendersBaneCard(Card):
    """Curse — Unplayable, Eternal, Ethereal.

    Source: AscendersBane.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Eternal, Unplayable, Ethereal
      CanBeGeneratedByModifiers = false (added by Ascension, not random curses)
    """
    id = "ascenders_bane"
    name = "Ascender's Bane"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    is_ethereal = True
    eternal = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
