from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_PRIZE_COSTS = (35, 75, 135)   # _prizeCosts
_PRIZE_DAMAGE = (5, 6, 7)      # _prizeDamage
_MIN_HP = 19                   # IsAllowed threshold


@register_event
class ColossalFlower(Event):
    """Colossal Flower — extract the current gold prize, or reach deeper for a
    bigger one (taking damage), eventually reaching the Pollinous Core relic.

    Source: ColossalFlower.cs
      IsAllowed: current HP >= 19
      EXTRACT_CURRENT_PRIZE: gain the current prize gold (35 / 75 / 135)
      REACH_DEEPER: take damage (5 / 6 / 7) and dig deeper; after 2 digs the
                    choice becomes 135 gold or the Pollinous Core relic (+ more
                    damage)
    """

    id = "colossal_flower"
    name = "Colossal Flower"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.digs = 0

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.hp >= _MIN_HP

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("EXTRACT_CURRENT_PRIZE", self._extract_current_prize),
            EventOption("REACH_DEEPER", self._reach_deeper),
        ]

    def _reach_deeper(self) -> None:
        self.run.lose_hp(_PRIZE_DAMAGE[self.digs])
        self.digs += 1
        if self.digs < 2:
            self._set_state(f"REACH_DEEPER_{self.digs}", [
                EventOption("EXTRACT_CURRENT_PRIZE", self._extract_current_prize),
                EventOption("REACH_DEEPER", self._reach_deeper),
            ])
        else:
            self._set_state("REACH_DEEPER_2", [
                EventOption("EXTRACT_INSTEAD", self._extract_instead),
                EventOption("POLLINOUS_CORE", self._obtain_pollinous_core),
            ])

    def _extract_current_prize(self) -> None:
        self.run.gain_gold(_PRIZE_COSTS[self.digs])
        self._finish("EXTRACT_CURRENT_PRIZE")

    def _extract_instead(self) -> None:
        self.run.gain_gold(_PRIZE_COSTS[self.digs])
        self._finish("EXTRACT_INSTEAD")

    def _obtain_pollinous_core(self) -> None:
        self.run.lose_hp(_PRIZE_DAMAGE[self.digs])
        self.run.add_relic("pollinous_core")
        self._finish("POLLINOUS_CORE")
