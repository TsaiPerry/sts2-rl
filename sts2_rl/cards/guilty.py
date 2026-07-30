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

    The countdown lives on the RUN's copy of the card: `RunState.finish_combat`
    dispatches `AfterCombatEnd` over `run.deck`, which is the sim's
    `Pile.Type == PileType.Deck`.
    """
    id = "guilty"
    name = "Guilty"
    card_type = CardType.CURSE
    rarity = CardRarity.CURSE
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True

    # Guilty.cs:13 -- `public const int maxCombats = 5`, and CanonicalVars'
    # DynamicVar("Combats", 5) is the same number counted down for the card
    # text (`Combats.BaseValue = 5 - CombatsSeen`, :35).
    MAX_COMBATS = 5

    def _init_vars(self) -> None:
        self._energy_cost = 0
        # `[SavedProperty] int CombatsSeen` (Guilty.cs:25-37).
        self.combats_seen = 0

    def after_combat_end(self, run) -> None:
        """Guilty.cs:45-56. Reaching this method at all IS the
        `pile.Type == PileType.Deck` test: the run dispatches it over
        `run.deck` only, so a Guilty that has already left stops counting.
        The removal goes through `remove_cards`, which fires
        `Hook.BeforeCardRemoved` as `CardPileCmd.RemoveFromDeck` does."""
        self.combats_seen += 1
        if self.combats_seen >= self.MAX_COMBATS:
            run.remove_cards([self])

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
