from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class NormalityCard(Card):
    """Curse — Unplayable; while in your hand, you cannot play more than
    3 cards per turn.

    Source: Normality.cs
      Cost -1 | Curse | Curse | TargetType.None
      Keywords: Unplayable
      ShouldPlay: while Normality is in the owner's hand, blocks every play
      (manual and auto — the AutoPlayType argument is ignored) once 3 card
      plays have started this turn (History.CardPlaysStarted).
    """
    id = "normality"
    name = "Normality"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True

    CARDS_PER_TURN = 3

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        if self.combat is None or self not in self.combat.player.hand:
            return True
        from ..history import CardPlayedEntry
        played = sum(
            1 for _ in self.combat.history.of_type(CardPlayedEntry, this_turn=True)
        )
        return played < self.CARDS_PER_TURN
