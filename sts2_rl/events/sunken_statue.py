from __future__ import annotations

from .base import Event, EventOption, register_event

_BASE_GOLD = 111     # GoldVar(111)
_GOLD_VARIANCE = 10  # NextInt(-10, 11)
_HP_LOSS = 7         # DynamicVar("HpLoss", 7)


@register_event
class SunkenStatue(Event):
    """Sunken Statue — take the Sword of Stone, or dive for gold.

    Source: SunkenStatue.cs
      CalculateVars: gold = 111 + NextInt(-10, 11)
      GRAB_SWORD:      obtain the Sword of Stone relic
      DIVE_INTO_WATER: gain the gold, lose 7 HP (unblockable, unpowered)
    """

    id = "sunken_statue"
    name = "Sunken Statue"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.gold = _BASE_GOLD

    def calculate_vars(self) -> None:
        self.gold = _BASE_GOLD + self.rng.randint(-_GOLD_VARIANCE, _GOLD_VARIANCE)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GRAB_SWORD", self._grab_sword),
            EventOption("DIVE_INTO_WATER", self._dive_into_water),
        ]

    def _grab_sword(self) -> None:
        self.run.add_relic("sword_of_stone")
        self._finish("GRAB_SWORD")

    def _dive_into_water(self) -> None:
        self.run.gain_gold(self.gold)
        self.run.lose_hp(_HP_LOSS)
        self._finish("DIVE_INTO_WATER")
