from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BASE_GOLD = 149  # GoldVar(149)


@register_event
class LuminousChoir(Event):
    """Luminous Choir — take a Spore Mind for two removals, or buy a relic.

    Source: LuminousChoir.cs
      IsAllowed: gold >= 149 (the canonical GoldVar) and the relic grab bag
                 has relics left
      CalculateVars: gold cost = 149 - NextInt(0, 50)
      REACH_INTO_THE_FLESH: remove 2 chosen cards, add a Spore Mind curse
      OFFER_TRIBUTE: pay the gold, obtain the next grab-bag relic
                     (locked when unaffordable)
    """

    id = "luminous_choir"
    name = "Luminous Choir"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.gold_cost = _BASE_GOLD

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _BASE_GOLD and run.has_available_relics()

    def calculate_vars(self) -> None:
        # `base.Rng.NextInt(0, 50)` — the event's own Rng (LuminousChoir.cs:30).
        er = self.event_rng
        discount = (er.next_int_range(0, 50) if er is not None
                    else self.rng.randint(0, 49))
        self.gold_cost = _BASE_GOLD - discount

    def initial_options(self) -> list[EventOption]:
        options = [EventOption("REACH_INTO_THE_FLESH", self._reach_into_the_flesh)]
        if self.run.gold >= self.gold_cost:
            options.append(EventOption("OFFER_TRIBUTE", self._offer_tribute))
        else:
            options.append(EventOption("OFFER_TRIBUTE_LOCKED", None))
        return options

    def _reach_into_the_flesh(self) -> None:
        chosen = self.run.select_cards("remove", self.run.removable_cards(), 2)
        self.run.remove_cards(chosen)
        self.run.add_card(make_card("spore_mind"))
        self._finish("REACH_INTO_THE_FLESH")

    def _offer_tribute(self) -> None:
        self.run.lose_gold(self.gold_cost)
        self.run.obtain_relic_from_grab_bag()
        self._finish("OFFER_TRIBUTE")
