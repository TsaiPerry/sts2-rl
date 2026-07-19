from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..cards import Card
    from ..run import RunState

_BASE_HP_LOSS = 3    # CurrentHpLoss = 3 + holds so far


@register_event
class SlipperyBridge(Event):
    """Slippery Bridge — drop the shown card, or cling on at mounting cost.

    Shared event (ModelDb.AllSharedEvents). Source: SlipperyBridge.cs
      IsAllowed: TotalFloor > 6 and every player's deck has a removable card
      OVERCOME:   remove the currently shown random card from the deck
      HOLD_ON_n:  take 3+n damage (n = holds so far), re-roll the shown card
                  (excluding the ids already shown), and ask again — forever

    The shown card starts as a random non-Basic removable card (falling back
    to any removable card when there are none); each re-roll excludes the
    previously shown card's id and every skipped instance (GetNewRandomCard).
    """

    id = "slippery_bridge"
    name = "Slippery Bridge"

    def __init__(self, run: RunState) -> None:
        super().__init__(run)
        self.shown_card: Card | None = None
        self._holds = 0
        self._skipped: set[int] = set()      # id()s of shown-then-skipped cards

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.total_floor > 6 and bool(run.removable_cards())

    def _roll_shown_card(self) -> None:
        from ..cards import CardRarity

        removable = self.run.removable_cards()
        if self.shown_card is None:
            candidates = [c for c in removable if c.rarity != CardRarity.BASIC]
        else:
            # Exclude the current card's id (GetType() in the source) and
            # every instance previously shown and skipped.
            self._skipped.add(id(self.shown_card))
            candidates = [
                c for c in removable
                if c.id != self.shown_card.id and id(c) not in self._skipped
            ]
        if not candidates:
            candidates = removable
        self.shown_card = self.rng.choice(candidates)

    def _suffix(self, holds: int) -> str:
        # GetHoldOnSuffix: numbered pages/options cap at LOOP after 7.
        return "LOOP" if holds >= 7 else str(holds)

    def _page_options(self) -> list[EventOption]:
        return [
            EventOption("OVERCOME", self._overcome),
            EventOption(f"HOLD_ON_{self._suffix(self._holds)}", self._hold_on),
        ]

    def initial_options(self) -> list[EventOption]:
        self._roll_shown_card()
        return self._page_options()

    def _overcome(self) -> None:
        self.run.remove_cards([self.shown_card])
        self._finish("OVERCOME")

    def _hold_on(self) -> None:
        self.run.lose_hp(_BASE_HP_LOSS + self._holds)
        self._holds += 1
        self._roll_shown_card()
        self._set_state(f"HOLD_ON_{self._suffix(self._holds - 1)}", self._page_options())
