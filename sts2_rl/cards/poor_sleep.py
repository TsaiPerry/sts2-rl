from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PoorSleepCard(Card):
    """Curse — Unplayable, Retain (never leaves your hand once drawn).

    Source: PoorSleep.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Unplayable, Retain
      CanBeGeneratedByModifiers = false
    """
    id = "poor_sleep"
    name = "Poor Sleep"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    retain = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
