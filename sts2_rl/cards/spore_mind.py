from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SporeMindCard(Card):
    """Curse (1E) — Exhaust; playable with no effect (pay 1 to get rid of it).

    Source: SporeMind.cs
      Cost 1 | Curse | Curse | TargetType.None
      Keywords: Exhaust (playable — no Unplayable keyword)
      CanBeGeneratedByModifiers = false
    """
    id = "spore_mind"
    name = "Spore Mind"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    exhausts = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
