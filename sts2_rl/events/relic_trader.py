from __future__ import annotations

from typing import TYPE_CHECKING

from ..actmap import stable_shuffle
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..relics import Relic
    from ..run import RunState


@register_event
class RelicTrader(Event):
    """Relic Trader — swap one of your relics for a mystery replacement.

    Shared event (ModelDb.AllSharedEvents). Source: RelicTrader.cs
      IsAllowed: acts 2-3, and the player owns >= 5 tradable relics
      TOP/MIDDLE/BOTTOM: give the i-th shown owned relic, obtain the i-th
        pre-pulled grab-bag relic (both triples are rolled when the event
        begins: 3 stable-shuffled owned tradables, 3 grab-bag pulls — the
        pulls are consumed from the bag whether or not they are chosen,
        exactly like PullNextRelicFromFront)
    """

    id = "relic_trader"
    name = "Relic Trader"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return (
            run.act_index != 0
            and sum(1 for r in run.relics if r.is_tradable) >= 5
        )

    def calculate_vars(self) -> None:
        # CalculateVars touches OwnedRelics then NewRelics — same order.
        owned = [r for r in self.run.relics if r.is_tradable]
        # `GetValidRelics(Owner).ToList().StableShuffle(base.Rng).Take(3)`
        # (RelicTrader.cs:51): the event's own Rng, and the stabilizing sort is
        # AbstractModel.CompareTo -> ModelId.CompareTo, an ordinal compare over
        # the UPPERCASE entry (ModelId.cs:49).
        er = self.event_rng
        self._owned: list[Relic] = stable_shuffle(
            owned, er if er is not None else self.rng,
            key=lambda r: r.id.upper())[:3]
        self._new: list[Relic] = []
        for _ in range(3):
            relic = self.run.pull_relic_from_front()
            if relic is None:
                break
            self._new.append(relic)

    def initial_options(self) -> list[EventOption]:
        keys = ("TOP", "MIDDLE", "BOTTOM")
        options = [
            EventOption(keys[i], lambda i=i: self._trade(i))
            for i in range(min(len(self._owned), len(self._new)))
        ]
        return options or [EventOption("PROCEED", lambda: self._finish("DONE"))]

    def _trade(self, index: int) -> None:
        self.run.relics.remove(self._owned[index])
        self.run.add_relic(self._new[index])
        self._finish("DONE")
