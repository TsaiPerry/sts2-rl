from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .creatures import Creature

if TYPE_CHECKING:
    from .combat import CombatCtx
    from .hooks import HookSystem
    from .powers import Power


class MoveType(Enum):
    ATTACK = "attack"
    BUFF = "buff"


@dataclass
class Intent:
    """What an enemy intends to do on its next turn.

    For ATTACK: damage is per-hit, hits is the number of hits.
    For BUFF:   buffs is a list of (PowerClass, amount) to apply to self.
    """
    move_type: MoveType
    damage: int = 0
    hits: int = 1
    buffs: list[tuple[type[Power], int]] = field(default_factory=list)

    @property
    def total_damage(self) -> int:
        return self.damage * self.hits


class Monster(Creature):
    """Base class for all enemies.  Subclasses must set min_hp / max_hp and
    implement current_intent and take_turn."""

    min_hp: int = 0
    max_hp: int = 0

    def __init__(self, hooks: HookSystem, rng: random.Random) -> None:
        hp = rng.randint(self.min_hp, self.max_hp)
        super().__init__(hp)
        self._hooks = hooks

    @property
    def current_intent(self) -> Intent:
        raise NotImplementedError

    def take_turn(self, ctx: CombatCtx) -> None:
        raise NotImplementedError

    def _execute_attack(self, ctx: CombatCtx, damage: int, hits: int) -> None:
        """Deal a multi-hit attack, stopping early if attacker or player dies."""
        from .cmds import DamageCmd
        for _ in range(hits):
            DamageCmd.deal(ctx.hooks, ctx.player, damage, dealer=self)
            if ctx.player.is_dead or self.is_dead:
                break


@dataclass
class Encounter:
    """A group of monsters that fight together in a single combat."""

    id: str
    monster_classes: list[type[Monster]]

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        return [cls(hooks, rng) for cls in self.monster_classes]


# ── Concrete monsters ──────────────────────────────────────────────────────

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
        from .powers import StrengthPower
        return Intent(move_type=MoveType.BUFF, buffs=[(StrengthPower, strength_gain)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from .cmds import PowerCmd
        intent = self.current_intent
        if intent.move_type == MoveType.ATTACK:
            self._execute_attack(ctx, intent.damage, intent.hits)
        else:
            for power_cls, amount in intent.buffs:
                PowerCmd.apply(ctx.hooks, self, power_cls, amount)
        self._advance_move()

    def _advance_move(self) -> None:
        self._move_key = self._TRANSITIONS[self._move_key]


# ── Default encounters ─────────────────────────────────────────────────────

FUZZY_WURM_ENCOUNTER = Encounter(
    id="fuzzy_wurm_crawler",
    monster_classes=[FuzzyWurmCrawler],
)
