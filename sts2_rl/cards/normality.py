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
        from ..history import CardPlayStartedEntry
        # Normality.cs:33 counts `History.CardPlaysStarted`, i.e. plays STARTED
        # (CardModel.cs:1930, before OnPlay) — not plays finished. The two agree
        # for simple sequential plays and diverge whenever a play is IN FLIGHT
        # while another card's playability is tested, which is what every
        # auto-play does: with two plays behind you, the card Havoc auto-plays
        # is the FOURTH started play and the game blocks it. Counting finished
        # plays let it through.
        started = sum(
            1
            for _ in self.combat.history.of_type(CardPlayStartedEntry,
                                                 this_turn=True)
        )
        return started < self.CARDS_PER_TURN
