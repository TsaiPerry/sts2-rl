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
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    @property
    def magic_number(self) -> int:
        """Normality.cs:26-31 -- `CalculatedVar("CalculatedCards")` =
        `CalculationBaseVar(3) + CalculationExtraVar(-1) * Math.Min(3,
        CardsPlayedThisTurn)`, i.e. plays remaining this turn -- a live
        countdown (3, 2, 1, 0), not a static printed number, and per the
        record "the single most decision-relevant number on the board".
        Overrides `Card.magic_number`'s `_MAGIC_ATTRS` scan (Normality sets
        none of those attrs) and mirrors the exact count `should_play_card`
        below already performs against `CardPlaysStarted` (Normality.cs:33).
        """
        if self.combat is None:
            return self.CARDS_PER_TURN
        from ..history import CardPlayStartedEntry
        started = sum(
            1
            for _ in self.combat.history.of_type(CardPlayStartedEntry,
                                                 this_turn=True)
        )
        return self.CARDS_PER_TURN - min(self.CARDS_PER_TURN, started)

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        if self.combat is None or self not in self.combat.player.hand:
            return True
        from ..history import CardPlayStartedEntry
        # Normality.cs:33 counts plays STARTED (CardModel.cs:1930, before
        # OnPlay), not finished — diverges from finished-count whenever a
        # play is in flight, e.g. Havoc auto-playing a 4th card mid-turn.
        started = sum(
            1
            for _ in self.combat.history.of_type(CardPlayStartedEntry,
                                                 this_turn=True)
        )
        return started < self.CARDS_PER_TURN
