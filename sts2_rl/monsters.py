from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from .creatures import Creature


class MoveType(Enum):
    ATTACK = "attack"
    BUFF = "buff"


@dataclass(frozen=True)
class Move:
    name: str
    move_type: MoveType
    damage: int = 0
    strength_gain: int = 0


class FuzzyWurmCrawler(Creature):
    MIN_HP = 55
    MAX_HP = 57

    _MOVES: dict[str, Move] = {
        "FIRST_ACID_GOOP": Move("Acid Goop", MoveType.ATTACK, damage=4),
        "INHALE":          Move("Inhale",    MoveType.BUFF,   strength_gain=7),
        "ACID_GOOP":       Move("Acid Goop", MoveType.ATTACK, damage=4),
    }

    _TRANSITIONS: dict[str, str] = {
        "FIRST_ACID_GOOP": "INHALE",
        "INHALE":          "ACID_GOOP",
        "ACID_GOOP":       "FIRST_ACID_GOOP",
    }

    def __init__(self, rng: random.Random | None = None) -> None:
        max_hp = (rng or random.Random()).randint(self.MIN_HP, self.MAX_HP)
        super().__init__(max_hp)
        self._move_key = "FIRST_ACID_GOOP"

    @property
    def current_move(self) -> Move:
        return self._MOVES[self._move_key]

    def advance_move(self) -> None:
        self._move_key = self._TRANSITIONS[self._move_key]
