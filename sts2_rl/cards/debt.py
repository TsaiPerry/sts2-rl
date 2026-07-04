from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DebtCard(Card):
    """Curse — Unplayable; at the end of your turn, lose 10 Gold.

    Source: Debt.cs
      Cost -1 | Curse | Curse | TargetType.None | GoldVar(10)
      Keywords: Unplayable; HasTurnEndInHandEffect
      OnTurnEndInHand: PlayerCmd.LoseGold(min(10, gold))

    The sim has no gold, so the turn-end effect is a no-op here; the card is
    otherwise a dead unplayable draw, matching the game.
    """
    id = "debt"
    name = "Debt"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
