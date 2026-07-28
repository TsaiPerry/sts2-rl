from __future__ import annotations

from typing import TYPE_CHECKING

from ..actmap import stable_shuffle
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_TAKE_TIME_HP_LOSS = 5    # TakeTimeHpLoss
_EXAMINE_HP_LOSS = 15     # ExamineHpLoss

# DollRoom._dolls, in source order.
_DOLLS = ("daughter_of_the_wind", "mr_struggles", "bing_bong")


@register_event
class DollRoom(Event):
    """Doll Room — take a doll blind, or pay HP to pick from more of them.

    Shared event (ModelDb.AllSharedEvents). Source: DollRoom.cs
      IsAllowed: act 2 only (CurrentActIndex == 1)
      RANDOM:         a random doll, free
      TAKE_SOME_TIME: 5 damage, then choose 1 of 2 (stable-shuffled)
      EXAMINE:        15 damage, then choose 1 of 3 (stable-shuffled)
    The dolls are Daughter of the Wind, Mr. Struggles and Bing Bong; the
    follow-up pages key their options on the relic id.

    The source's doll-room ambience (BeforeEventStarted/OnEventFinished) is
    audio-only and not modeled.
    """

    id = "doll_room"
    name = "Doll Room"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index == 1

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("RANDOM", self._choose_random),
            EventOption("TAKE_SOME_TIME", self._take_some_time),
            EventOption("EXAMINE", self._examine),
        ]

    def _take(self, relic_id: str) -> None:
        self.run.add_relic(relic_id)
        self._finish(relic_id.upper())

    def _offer(self, page: str, count: int) -> None:
        # `_dolls.ToList().StableShuffle(base.Rng)` (DollRoom.cs:117/132) —
        # DollChoice.CompareTo defers to the relic's ModelId, so the sort key
        # is the UPPERCASE entry, and the shuffle is on the event's own Rng.
        er = self.event_rng
        dolls = stable_shuffle(
            list(_DOLLS), er if er is not None else self.rng, key=str.upper,
        )[:count]
        self._set_state(page, [
            EventOption(rid, lambda r=rid: self._take(r)) for rid in dolls
        ])

    def _choose_random(self) -> None:
        # `base.Rng.NextItem(_dolls)` (DollRoom.cs:108).
        er = self.event_rng
        self._take(er.next_item(_DOLLS) if er is not None
                   else self.rng.choice(_DOLLS))

    def _take_some_time(self) -> None:
        self.run.lose_hp(_TAKE_TIME_HP_LOSS)
        self._offer("TAKE_SOME_TIME", 2)

    def _examine(self) -> None:
        self.run.lose_hp(_EXAMINE_HP_LOSS)
        self._offer("EXAMINE", 3)
