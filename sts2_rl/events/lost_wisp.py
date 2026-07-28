from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event

_BASE_GOLD = 60  # GoldVar(60)


@register_event
class LostWisp(Event):
    """Lost Wisp — claim the wisp (a relic and a Decay curse), or search for
    gold.

    Source: LostWisp.cs
      CalculateVars: gold = 60 + NextInt(-15, 16)
      CLAIM:  add a Decay curse and obtain the Lost Wisp relic
      SEARCH: gain the gold
    """

    id = "lost_wisp"
    name = "Lost Wisp"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.gold = _BASE_GOLD

    def calculate_vars(self) -> None:
        # `base.Rng.NextInt(-15, 16)` — the event's own Rng (LostWisp.cs:44).
        er = self.event_rng
        variance = (er.next_int_range(-15, 16) if er is not None
                    else self.rng.randint(-15, 15))
        self.gold = _BASE_GOLD + variance

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("CLAIM", self._claim),
            EventOption("SEARCH", self._search),
        ]

    def _claim(self) -> None:
        self.run.add_card(make_card("decay"))
        self.run.add_relic("lost_wisp")
        self._finish("CLAIM")

    def _search(self) -> None:
        self.run.gain_gold(self.gold)
        self._finish("SEARCH")
