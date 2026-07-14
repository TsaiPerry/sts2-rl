from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event

_SMALL_CHEST_GOLD = 60   # DynamicVar("SmallChestGold", 60)
_LARGE_CHEST_GOLD = 333  # DynamicVar("LargeChestGold", 333)


@register_event
class SunkenTreasury(Event):
    """Sunken Treasury — take the small chest, or the large one with a curse.

    Source: SunkenTreasury.cs
      CalculateVars: SmallChestGold += NextInt(16) - 8; LargeChestGold +=
                     NextInt(61) - 30
      FIRST_CHEST:   gain the small gold
      SECOND_CHEST:  gain the large gold and add a Greed curse
    """

    id = "sunken_treasury"
    name = "Sunken Treasury"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.small_gold = _SMALL_CHEST_GOLD
        self.large_gold = _LARGE_CHEST_GOLD

    def calculate_vars(self) -> None:
        self.small_gold = _SMALL_CHEST_GOLD + (self.rng.randrange(16) - 8)
        self.large_gold = _LARGE_CHEST_GOLD + (self.rng.randrange(61) - 30)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("FIRST_CHEST", self._first_chest),
            EventOption("SECOND_CHEST", self._second_chest),
        ]

    def _first_chest(self) -> None:
        self.run.gain_gold(self.small_gold)
        self._finish("FIRST_CHEST")

    def _second_chest(self) -> None:
        self.run.gain_gold(self.large_gold)
        self.run.add_card(make_card("greed"))
        self._finish("SECOND_CHEST")
