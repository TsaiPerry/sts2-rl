from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem


class FuzzyWurmCrawler(Monster):
    min_hp = 55
    max_hp = 57

    # (move_type, damage, hits, strength_gain)
    _MOVES: dict[str, tuple[MoveType, int, int, int]] = {
        "FIRST_ACID_GOOP": (MoveType.ATTACK, 4, 1, 0),
        "INHALE":          (MoveType.BUFF,   0, 0, 7),
        "ACID_GOOP":       (MoveType.ATTACK, 4, 1, 0),
    }

    _TRANSITIONS: dict[str, str] = {
        "FIRST_ACID_GOOP": "INHALE",
        "INHALE":          "ACID_GOOP",
        "ACID_GOOP":       "FIRST_ACID_GOOP",
    }

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "FIRST_ACID_GOOP"

    @property
    def current_intent(self) -> Intent:
        move_type, damage, hits, strength_gain = self._MOVES[self._move_key]
        if move_type == MoveType.ATTACK:
            return Intent(move_type=MoveType.ATTACK, damage=damage, hits=hits)
        from ..powers import StrengthPower
        return Intent(move_type=MoveType.BUFF, buffs=[(StrengthPower, strength_gain)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        intent = self.current_intent
        if intent.move_type == MoveType.ATTACK:
            self._execute_attack(ctx, intent.damage, intent.hits)
        else:
            for power_cls, amount in intent.buffs:
                PowerCmd.apply(ctx.hooks, self, power_cls, amount)
        self._advance_move()

    def _advance_move(self) -> None:
        self._move_key = self._TRANSITIONS[self._move_key]


FUZZY_WURM_ENCOUNTER = Encounter(
    id="fuzzy_wurm_crawler",
    monster_classes=[FuzzyWurmCrawler],
)
