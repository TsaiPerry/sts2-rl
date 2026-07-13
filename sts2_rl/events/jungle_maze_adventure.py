from __future__ import annotations

from .base import Event, EventOption, register_event

_SOLO_GOLD = 150       # DynamicVar("SoloGold", 150)
_SOLO_HP_LOSS = 18     # DamageVar("SoloHp", 18, Unblockable | Unpowered)
_JOIN_GOLD = 50        # DynamicVar("JoinForcesGold", 50)
_GOLD_VARIANCE = 15.0  # NextFloat(-15, 15)


@register_event
class JungleMazeAdventure(Event):
    """Jungle Maze Adventure — brave the maze alone or join forces.

    Source: JungleMazeAdventure.cs
      CalculateVars: SoloGold = 150 + NextFloat(-15, 15),
                     JoinForcesGold = 50 + NextFloat(-15, 15)
      SOLO_QUEST:  lose 18 HP (unblockable, unpowered), gain SoloGold
      JOIN_FORCES: gain JoinForcesGold
    Gold amounts stay fractional until PlayerCmd.GainGold truncates them.
    """

    id = "jungle_maze_adventure"
    name = "Jungle Maze Adventure"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.solo_gold: float = _SOLO_GOLD
        self.join_forces_gold: float = _JOIN_GOLD

    def calculate_vars(self) -> None:
        self.solo_gold = _SOLO_GOLD + self.rng.uniform(-_GOLD_VARIANCE, _GOLD_VARIANCE)
        self.join_forces_gold = _JOIN_GOLD + self.rng.uniform(-_GOLD_VARIANCE, _GOLD_VARIANCE)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("SOLO_QUEST", self._solo_quest),
            EventOption("JOIN_FORCES", self._join_forces),
        ]

    def _solo_quest(self) -> None:
        self.run.lose_hp(_SOLO_HP_LOSS)
        self.run.gain_gold(self.solo_gold)
        self._finish("SOLO_QUEST")

    def _join_forces(self) -> None:
        self.run.gain_gold(self.join_forces_gold)
        self._finish("JOIN_FORCES")
