from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..creatures import Creature

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem
    from ..powers import Power


class MoveType(Enum):
    """Full intent vocabulary, mirroring STS2's IntentType."""

    ATTACK = "attack"
    BUFF = "buff"
    DEBUFF = "debuff"                # applies a power debuff to the player
    DEBUFF_STRONG = "debuff_strong"
    DEFEND = "defend"                # gains block
    ESCAPE = "escape"                # flees combat
    HEAL = "heal"
    HIDDEN = "hidden"
    SUMMON = "summon"                # adds creatures to combat
    SLEEP = "sleep"
    STUN = "stun"                    # skipping this turn (stunned)
    STATUS_CARD = "status_card"      # shuffles status cards into player piles
    CARD_DEBUFF = "card_debuff"      # afflicts the player's cards
    DEATH_BLOW = "death_blow"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """What an enemy intends to do on its next turn.

    move_type is the primary intent; `also` carries secondary intent types for
    moves that do several things (mirrors STS2 MoveStates holding multiple
    intents, e.g. an attack that also gains block shows ATTACK + DEFEND).

    For ATTACK: damage is per-hit, hits is the number of hits.
    For BUFF:   buffs is a list of (PowerClass, amount) to apply to self.
    """
    move_type: MoveType
    damage: int = 0
    hits: int = 1
    buffs: list[tuple[type[Power], int]] = field(default_factory=list)
    also: tuple[MoveType, ...] = ()

    @property
    def total_damage(self) -> int:
        return self.damage * self.hits

    def has(self, move_type: MoveType) -> bool:
        """True if move_type is the primary or a secondary intent."""
        return self.move_type == move_type or move_type in self.also


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
        """Deal a multi-hit attack, stopping early if attacker or player dies.

        The before/after hooks bracket the whole attack command (all hits),
        mirroring AttackCommand's BeforeAttack/AfterAttack."""
        from ..cmds import DamageCmd
        ctx.hooks.before_attack(self)
        for _ in range(hits):
            DamageCmd.deal(ctx.hooks, ctx.player, damage, dealer=self)
            if ctx.player.is_dead or self.is_dead:
                break
        ctx.hooks.after_attack(self)


@dataclass
class Encounter:
    """A group of monsters that fight together in a single combat."""

    id: str
    monster_classes: list[type[Monster]]

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        return [cls(hooks, rng) for cls in self.monster_classes]
