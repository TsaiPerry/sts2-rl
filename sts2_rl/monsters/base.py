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

    def adjust_hp_after_added(self, teammates: "list[Monster]") -> None:
        """MonsterModel.AfterAddedToRoom's HP fix-up, applied AFTER the parity
        Niche roll has set this creature's max HP (CombatState.CreateCreature
        rolls first, the room-add hook then reshapes the value).

        Default: nothing. Overridden by monsters whose source hook rewrites
        MaxHp (DecimillipedeSegment's even-and-unique pass). `teammates` are
        the other enemies already on this side, with their final HP."""

    def __init__(self, hooks: HookSystem, rng: random.Random) -> None:
        hp = rng.randint(self.min_hp, self.max_hp)
        super().__init__(hp)
        self._hooks = hooks
        # Stable per-combat creature id (CombatState.CombatId; attach order,
        # enemies numbered 1..N). Assigned by Combat/CreatureCmd.add; the
        # recording targets cards by it (PlayCard <card> <CombatId>), so it must
        # survive enemy-list reordering (e.g. Ovicopter egg slots). None until
        # the creature joins a combat.
        self.net_id: int | None = None
        # MonsterMoveStateMachine._performedFirstMove, tracked at the combat
        # level so the player-turn-start intent pass can honour
        # FindNextMoveState's `!_performedFirstMove && IsMove -> return` guard
        # (MonsterMoveStateMachine.cs:60-63) for the hand-rolled monsters too:
        # they have no machine, so nothing else would stop the pass advancing a
        # monster that has not acted yet (a turn-1 enemy, or a mid-combat
        # spawn). Set by CombatState._run_enemy_turns, which is where
        # MonsterModel.PerformMove calls OnMovePerformed.
        self.performed_first_move = False

    @property
    def current_intent(self) -> Intent:
        raise NotImplementedError

    def take_turn(self, ctx: CombatCtx) -> None:
        raise NotImplementedError

    def telegraph_next_move(self) -> None:
        """Advance/roll the next move without performing anything this turn.

        Mirrors Creature.PrepareForNextTurn, which the game calls for every
        enemy at player-turn-start unconditionally — including one that was
        stunned this round (its synthetic STUNNED move is performed like any
        other, so the roll still happens). Monsters with a next-move roll
        override this; the default is a no-op for monsters with nothing to
        advance (fixed single-move loops, etc.). The only caller is
        CombatState._roll_enemy_intents."""
        pass

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
    # EncounterModel.ShouldGiveRewards — False suppresses the post-combat
    # reward screen entirely (Battleworn Dummy's training fights).
    should_give_rewards: bool = True
    # EncounterModel.MinGoldReward/MaxGoldReward are virtual: an encounter may
    # override the room type's default range (the Fake Merchant pins 300).
    # None on both = use the room-type range (rewards.GOLD_REWARD_RANGES).
    min_gold: int | None = None
    max_gold: int | None = None

    @property
    def entry(self) -> str:
        """The game's ModelId.Entry (StringHelper.Slugify of the encounter
        class name — UPPER_SNAKE_CASE), used to seed the per-encounter monster-
        selection Rng (EncounterModel.GenerateMonstersWithSlots). The sim's
        lowercase `id` is that slug lowercased, so upper-casing recovers it for
        every encounter whose id matches its class-name slug."""
        return self.id.upper()

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Fixed composition draws no RNG, so the parity selection_rng (when
        # present) is simply unused here.
        return [cls(hooks, rng) for cls in self.monster_classes]
