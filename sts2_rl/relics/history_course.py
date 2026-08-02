from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class HistoryCourse(Relic):
    """HistoryCourse.cs — Event-pool relic, granted by War Historian Repy's
    UnlockCage option (WarHistorianRepy.cs:96-100).

    `AfterAutoPrePlayPhaseEntered` (:17-40): skipped on the owner's first
    turn (`PlayerCombatState.TurnNumber == 1`, :19). Otherwise looks up
    `CombatManager.Instance.History.CardPlaysFinished.LastOrDefault(...)`
    for the last entry where the played card's owner is this relic's owner,
    `HappenedLastPlayerTurn` is true (stamped turn number == owner's current
    TurnNumber - 1), the card's type is Attack or Skill (`(uint)(type-1) <=
    1u` tests exactly the two enum values immediately after `None`), and the
    card is not itself a dupe (`!e.CardPlay.Card.IsDupe`). If found: `Flash()`
    (VFX only, no sim counterpart, per `relics/ruined_helmet.py`'s precedent)
    then `CardCmd.AutoPlay(choiceContext, cardModel.CreateDupe(), null)` — a
    fresh dupe, free, auto-targeted (no chosen target).

    The sim's history entries are stamped with `CombatState.round_number`
    (`history.py`'s `HistoryEntry.turn`), not a per-player TurnNumber
    snapshot the way `CombatHistoryEntry` is in the source. The two only
    diverge on an extra player turn (SwitchSides bumping TurnNumber without
    bumping RoundNumber, per `history.py`'s own docstring) — a case no other
    sim relic's "last turn" query resolves differently either. Comparing
    against `self.turn - 1` (== `combat.turn`, the sim's own TurnNumber
    counterpart, distinct from `round_number`) is the best-effort match; see
    this file's test for the ordinary (non-extra-turn) case this covers.

    The sim is single-player only, so `CardPlay.Card.Owner == base.Owner` and
    `player != base.Owner` (:19) are always true and are not encoded as
    explicit checks here.
    """

    id = "history_course"
    name = "History Course"
    rarity = RelicRarity.EVENT

    def after_auto_pre_play_phase_entered(self, player: "PlayerCombatState") -> None:
        if self.turn == 1:
            return
        from ..cards.base import CardType, create_clone
        from ..history import CardPlayedEntry

        target_turn = self.turn - 1
        found = None
        for entry in self.combat.history.of_type(CardPlayedEntry):
            if entry.turn != target_turn:
                continue
            card = entry.card
            if card.card_type not in (CardType.ATTACK, CardType.SKILL):
                continue
            if getattr(card, "is_dupe", False):
                continue
            found = card  # keep overwriting -> LastOrDefault semantics
        if found is None:
            return
        dupe = create_clone(found)
        dupe.is_dupe = True
        dupe.exhausts = False  # CreateDupe removes CardKeyword.Exhaust
        self.combat.auto_play_card(dupe)
