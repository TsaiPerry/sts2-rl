from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class GuiltyCard(Card):
    """Curse — Unplayable; removes itself from the deck after 5 combats.

    Source: Guilty.cs
      Cost -1 | Curse | Curse | TargetType.None | DynamicVar("Combats", 5)
      Keywords: Unplayable
      AfterCombatEnd: increments CombatsSeen; at 5, CardPileCmd.RemoveFromDeck.

    The countdown/removal happens between combats on the persistent deck,
    which the sim doesn't model — inside a single combat Guilty is just a dead
    unplayable card, matching the game.
    """
    id = "guilty"
    name = "Guilty"
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
