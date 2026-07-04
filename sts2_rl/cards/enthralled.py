from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class EnthralledCard(Card):
    """Curse (2E) — Eternal; playable with no effect. While in your hand, you
    cannot play any other card until it is played.

    Source: Enthralled.cs
      Cost 2 | Curse | Curse | TargetType.None
      Keywords: Eternal (playable — no Unplayable keyword; no Exhaust, so it
      goes to the discard pile when played)
      ShouldPlay: while an Enthralled is in the owner's hand, only Enthralled
      cards may be manually played; auto-plays (AutoPlayType != None) are
      always allowed.
      CanBeGeneratedByModifiers = false
    """
    id = "enthralled"
    name = "Enthralled"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    eternal = True
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        if self.combat is None or self not in self.combat.player.hand:
            return True
        if isinstance(card, EnthralledCard):
            return True
        return auto_play
