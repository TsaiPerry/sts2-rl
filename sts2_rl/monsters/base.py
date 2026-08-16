from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..creatures import Creature
from ..hooks import CAT_MONSTER

if TYPE_CHECKING:
    from ..actmap import AscensionLevel
    from ..combat import CombatCtx
    from ..hooks import HookSystem
    from ..powers import Power


def asc_value(hooks: "HookSystem", level: "AscensionLevel", asc_val, base):
    """AscensionHelper.GetValueIfAscension (AscensionHelper.cs:22-47): the
    ascension value when the run has `level`, the base value otherwise."""
    return asc_val if hooks.ascension >= int(level) else base


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
    # `MoveState`'s empty `params AbstractIntent[]` (BattleFriendV1/2/3.cs:28's
    # NOTHING_MOVE) — a move that telegraphs literally NOTHING. Distinct from
    # both of the sim's other two placeholder values: UNKNOWN mirrors C#'s
    # real `UnknownIntent` (a displayed "?" glyph — used here only by
    # `monsters/state_machine.py`'s transient UNSET_MOVE sentinel, which is a
    # different concept: "no move has been rolled yet"), and HIDDEN mirrors
    # C#'s real `HiddenIntent` (a real, registered intent entry with no
    # sprite/tip — DecimillipedeSegment's DEAD_MOVE). NONE mirrors neither
    # class: C# never constructs an intent object for it at all (`params
    # AbstractIntent[] intents` receives zero arguments). No `Intent.has()`
    # check anywhere ever tests for it and no `also` tuple ever holds it, so
    # every encoder flag reads False for it — the same "nothing lit up" the
    # empty C# array produces — without the encoder needing a special case.
    NONE = "none"


@dataclass
class Intent:
    """What an enemy intends to do on its next turn.

    move_type is the primary intent; `also` carries secondary intent types for
    moves that do several things (mirrors STS2 MoveStates holding multiple
    intents, e.g. an attack that also gains block shows ATTACK + DEFEND).

    For ATTACK: damage is per-hit, hits is the number of hits.
    For BUFF:   buffs is a list of (PowerClass, amount) to apply to self.
    For a StatusIntent (move_type or a member of `also` is STATUS_CARD):
        status_count carries the C# `StatusIntent.CardCount` — how many
        status cards are about to land. The spec has EIGHTEEN
        `new StatusIntent(` sites and the sim has a 1:1 construction for
        each; as of 2026-08-06 EIGHT set the count (Aeonglass, Test Subject,
        The Insatiable, Vantom, Noisebot, LeafSlimeS, LeafSlimeM, TwigSlimeM)
        and TEN still leave it None — see `monster/_intent_count_lost`,
        which is open, not closed. `test_monster_tier_families.py`'s census
        ledger goes RED the moment that 8-of-18 split changes.
        Every other Intent construction leaves it at its default (None), and
        the observation encoder (full_env.py:571) still reads only the
        STATUS_CARD flag bit, not this value — the count is carried but
        unencoded (a checkpoint-tier concern, not this mechanism's).
    """
    move_type: MoveType
    damage: int = 0
    hits: int = 1
    buffs: list[tuple[type[Power], int]] = field(default_factory=list)
    also: tuple[MoveType, ...] = ()
    status_count: int | None = None

    @classmethod
    def none(cls) -> "Intent":
        """A `MoveState` built with C#'s empty `params AbstractIntent[]` — no
        telegraph at all (BattleFriendV1/2/3.cs:28's NOTHING_MOVE). See
        `MoveType.NONE` for why this is not `UNKNOWN` or `HIDDEN`."""
        return cls(MoveType.NONE)

    @property
    def total_damage(self) -> int:
        return self.damage * self.hits

    def has(self, move_type: MoveType) -> bool:
        """True if move_type is the primary or a secondary intent."""
        return self.move_type == move_type or move_type in self.also


# ---------------------------------------------------------------------------
# R3: per-enemy intent history (OBS_SCHEMA.md §7's R3 section, superseded by
# this constant + the recorder in combat.py).
#
# Census (state_machine.py's RandomBranchState.add_branch, plus the
# hand-rolled monsters that reimplement the same primitive via
# weighted_branch_pick): the deepest COOLDOWN window any ported monster ships
# is 3 (Flyconid's V_SPORES cooldown=3, FakeMerchant's ENRAGE cooldown=3,
# TwoTailedRat's SCREECH cooldown=3 — `monsters/overgrowth/flyconid.py`,
# `monsters/fake_merchant.py`, `monsters/underdocks/two_tailed_rat.py`); the
# deepest CAN_REPEAT_X_TIMES budget is max_times=2 (Knights' SOUL_SLASH,
# ScrollOfBiting's CHEW, FlailKnight's FLAIL/RAM, HunterKiller's PUNCTURE,
# FossilStalker's repeated move); CANNOT_REPEAT is a 1-move window.
# USE_ONLY_ONCE is excluded from this measurement on purpose: it gates on
# "has this move EVER happened this combat", a permanent flag, not a
# recency window — no bounded history depth reconstructs it, and none is
# expected to. 3 turns of displayed history is therefore sufficient to
# recover every ported repeat/cooldown gate from what the player has
# actually seen; a larger N would be dead weight.
MAX_INTENT_HISTORY = 3


def intent_flags(intent: "Intent", stunned: bool = False) -> tuple:
    """The 9 admissible ``MoveType`` booleans a displayed intent contributes
    to an enemy observation row, in the fixed order (attack, defend, buff,
    debuff[-strong]/card_debuff merged, status_card, summon, escape, heal,
    stun[/sleep] merged) ``full_env._enemy_floats`` has always used for the
    CURRENT intent. Factored out here so the R3 history recorder
    (``CombatState._record_intent_history``) computes the identical merge
    the current-intent encoder does, rather than keeping a second,
    independently-maintained copy that could silently drift from it."""
    return (
        intent.has(MoveType.ATTACK),
        intent.has(MoveType.DEFEND),
        intent.has(MoveType.BUFF),
        intent.has(MoveType.DEBUFF)
        or intent.has(MoveType.DEBUFF_STRONG)
        or intent.has(MoveType.CARD_DEBUFF),
        intent.has(MoveType.STATUS_CARD),
        intent.has(MoveType.SUMMON),
        intent.has(MoveType.ESCAPE),
        intent.has(MoveType.HEAL),
        intent.has(MoveType.STUN) or intent.has(MoveType.SLEEP) or stunned,
    )


@dataclass(frozen=True)
class IntentHistoryEntry:
    """One net_id-keyed snapshot of a previously-DISPLAYED intent (R3).

    Captured once per player turn, immediately before the enemy's intent is
    rerolled (``CombatState._record_intent_history``) — never derived lazily
    from a stored ``Intent`` object, because the attack-preview numbers
    (``per_hit``/``hits``/``total``) depend on the player's block/Strength/
    Vulnerable at the moment the intent was actually shown, state that is
    gone by the time an observation is built later.

    ``post_block`` is deliberately NOT captured here (OBS_SCHEMA.md's R3
    section has the full reasoning): it is a derived combination of a
    displayed number (damage) and the player's OWN block at that fleeting
    moment, which a player reconstructs trivially in the instant but does
    not retain as a discrete remembered fact the way "it hit me for 12" is
    retained — unlike ``total``, a pure function of the two numbers
    (``per_hit``, ``hits``) already co-displayed on the same icon, with no
    additional state involved.
    """

    flags: tuple  # 9-tuple, see intent_flags()
    per_hit: int | None
    hits: int | None
    total: int | None
    status_count: int | None


class Monster(Creature):
    """Base class for all enemies.  Subclasses must set min_hp / max_hp and
    implement current_intent and take_turn."""

    min_hp: int = 0
    max_hp: int = 0
    # Chomper.cs:28-30 pathfinder pattern: `MinInitialHp`/`MaxInitialHp` are
    # C# PROPERTIES read dynamically (AscensionHelper.GetValueIfAscension),
    # not fixed fields -- a monster whose ToughEnemies (asc 8+) HP range
    # differs from its base range sets these two class attrs; None (the
    # default) means "no override", i.e. every monster the game itself does
    # not scale under ToughEnemies. See __init__'s roll below for the gate.
    min_hp_asc: int | None = None
    max_hp_asc: int | None = None

    # `CombatState.IterateHookListeners` adds `creature.Monster` to the listener
    # list right after that creature's Powers (CombatState.cs:417-421); the sim's
    # Monster IS its own MonsterModel, so it registers itself as that listener.
    hook_category = CAT_MONSTER

    # Mirrors `Creature.CombatState == null` as an EVENT (set when
    # `CombatState.RemoveCreature` actually nulls the back-pointer, at
    # CreatureCmd.cs:529 death / :601 escape) -- NOT the same as
    # `is_removed_from_combat`, which is a PREDICTION true as soon as HP hits 0,
    # before the C# back-pointer is nulled (two statements after `Hook.AfterDeath`,
    # CreatureCmd.cs:519 vs :523-531). Using the prediction here would drop a
    # dying monster from its own AfterDeath / ShouldDie checks (KinPriest.cs:
    # 104-107 is one of eight self-death-only AfterDeath overrides affected).
    # `is_removed_from_combat` stays correct for its own callers and is untouched.
    combat_removal_committed: bool = False

    def hook_contains(self) -> bool:
        """`CombatState.Contains`' MonsterModel arm (CombatState.cs:585):
        `monsterModel.Creature.CombatState != null` — the ONLY leg; a monster
        listener is not tested against HasBeenRemovedFromState or an owner
        flag.

        Note what this does NOT exclude: a creature that is DEAD but still in
        the combat — a death-vetoed corpse or a withered Decimillipede segment
        (the `:523-531` block never ran), and a creature in the middle of its
        own death sequence (it has not run YET) — all still pass, exactly as
        in C#.
        """
        return not self.combat_removal_committed

    def adjust_hp_after_added(self, teammates: "list[Monster]") -> None:
        """MonsterModel.AfterAddedToRoom's HP fix-up, applied AFTER the parity
        Niche roll has set this creature's max HP (CombatState.CreateCreature
        rolls first, the room-add hook then reshapes the value).

        Default: nothing. Overridden by monsters whose source hook rewrites
        MaxHp (DecimillipedeSegment's even-and-unique pass). `teammates` are
        the other enemies already on this side, with their final HP."""

    def __init__(self, hooks: HookSystem, rng: random.Random) -> None:
        # Chomper.cs:28-30 pathfinder: MinInitialHp/MaxInitialHp swap to the
        # ToughEnemies (asc 8+) range when the subclass sets one. Exactly one
        # randint call either way -- only the BOUNDS branch, never the draw
        # itself -- so asc-0 rng streams are byte-identical to before this.
        from ..actmap import AscensionLevel
        use_asc = (
            self.min_hp_asc is not None
            and self.max_hp_asc is not None
            and hooks is not None
            and hooks.ascension >= int(AscensionLevel.TOUGH_ENEMIES)
        )
        lo, hi = (self.min_hp_asc, self.max_hp_asc) if use_asc else (self.min_hp, self.max_hp)
        hp = rng.randint(lo, hi)
        super().__init__(hp)
        self._hooks = hooks
        # Stable per-combat creature id (CombatState.CombatId; attach order,
        # enemies numbered 1..N). Assigned by Combat/CreatureCmd.add; the
        # recording targets cards by it (PlayCard <card> <CombatId>), so it must
        # survive enemy-list reordering (e.g. Ovicopter egg slots). None until
        # the creature joins a combat.
        self.net_id: int | None = None
        # Intent DISPLAYED for the turn this enemy is about to perform, snapshotted
        # by `CombatState._perform_move` right before `take_turn` runs. Needed
        # because hand-rolled monsters advance their own move-key INSIDE
        # `take_turn`, so a live re-read at the next player-turn start would see
        # the NEXT move, not the one just performed. MachineMonster advances only
        # in `telegraph_next_move` so it stays sticky and needs no snapshot; this
        # is a no-op for it. Sole reader: `CombatState._record_intent_history`.
        self.displayed_intent: "Intent | None" = None
        # MonsterMoveStateMachine._performedFirstMove, tracked here so hand-rolled
        # monsters (no machine) also honour FindNextMoveState's
        # `!_performedFirstMove && IsMove -> return` guard
        # (MonsterMoveStateMachine.cs:60-63). Set by CombatState._run_enemy_turns.
        self.performed_first_move = False
        # `MonsterModel.SpawnedThisTurn` (MonsterModel.cs:247-258): both the
        # initial roster and every mid-combat spawn call SetUpForCombat(), which
        # sets this True, so defaulting True at construction covers both. Cleared
        # once per enemy turn (`CombatState._run_enemy_turns`' OnSideSwitch) and
        # read by the move loop to skip PerformMove for a creature that joined
        # the fight this same enemy turn (Creature.cs:706-716).
        self.spawned_this_turn = True
        # `MonsterModel.IsPerformingMove` (MonsterModel.cs:137/440/447). Read by
        # CreatureCmd.cs:527 to REFUSE the death-removal RemoveCreature call while
        # the monster is mid-move; PerformMove's tail (:448-451) completes the
        # deferred removal once the move returns.
        self.is_performing_move = False
        # MonsterModel joins the hook walk (CombatState.cs:420); registered here
        # at construction since both creature-addition paths build the object and
        # append it to `combat.enemies` in the same step. Exception: combat SETUP
        # builds the whole roster before `CombatState.enemies` is assigned, so
        # `_merge_extras` seats those in their category tail instead -- membership
        # matters here, not registration order.
        # `hooks` is None for a monster built outside any combat (state-machine
        # construction tests); nothing to register with in that case.
        if hooks is not None:
            hooks.register(self)

    @property
    def has_rolled_a_move(self) -> bool:
        """False only while the creature still holds `MonsterModel.NextMove`'s
        initial `new MoveState()` — UNSET_MOVE (MonsterModel.cs:239,
        MoveState.cs:42-45), i.e. an enemy-side spawn that
        `CombatManager.AfterCreatureAdded`'s `CurrentSide == Player` gate
        declined to roll. Hand-rolled monsters pick their move in __init__ and
        have no such window, so the default is True."""
        return True

    @property
    def has_rolled_a_move(self) -> bool:
        """False only while the creature still holds `MonsterModel.NextMove`'s
        initial `new MoveState()` — UNSET_MOVE (MonsterModel.cs:239,
        MoveState.cs:42-45), i.e. an enemy-side spawn that
        `CombatManager.AfterCreatureAdded`'s `CurrentSide == Player` gate
        declined to roll. Hand-rolled monsters pick their move in __init__ and
        have no such window, so the default is True."""
        return True

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
    # `EncounterModel.Slots` — the NAMED row this encounter's creatures occupy,
    # in display order. Only encounters whose summons must land at a particular
    # position declare one (FabricatorNormal.cs:19, OvicopterNormal.cs:16); an
    # empty row means "no slot rule", which is what every other encounter has,
    # and then a spawn simply appends.
    slots: tuple[str, ...] = ()
    # The slot each of `monster_classes` is seeded into, positionally — the
    # `(MonsterModel, string?)` pairs `GenerateMonsters` returns
    # (FabricatorNormal.cs:46-49, OvicopterNormal.cs:36-39). None = unslotted.
    monster_slots: tuple[str | None, ...] = ()
    # `ModelId.Entry` where it is NOT `id.upper()` — see the `entry` property.
    # Nine sim ids are not their C# class name's slug (the sim drops tier
    # suffixes, and the event-wired encounters drop `_ENCOUNTER` entirely);
    # each of those declares the real slug here. Pinned for all 87 encounters
    # by test/test_encounter_entry_slugs.py.
    entry_slug: str | None = None

    def get_next_slot(self, combat) -> str:
        """`EncounterModel.GetNextSlot` (EncounterModel.cs:245-248) —
        `Slots.FirstOrDefault(s => Enemies.All(c => c.SlotName != s),
        string.Empty)`.

        Note the default: the EMPTY STRING, not null. A caller handed `""` (the
        row is full) passes it straight to CreatureCmd.Add, and `""` is not in
        Slots, so `Slots.IndexOf` returns -1 and the creature sorts to the FRONT.
        The Fabricator never reaches it because CanFabricate caps the bots at 4,
        but the value is reproduced rather than smoothed over.
        """
        return next((s for s in self.slots if s not in self._occupied(combat)), "")

    def last_free_slot(self, combat) -> str | None:
        """`Slots.LastOrDefault(s => Enemies.All(c => c.SlotName != s))`
        (Ovicopter.cs:87) — the OTHER end of the row, and with no default
        argument, so a full row yields None and the caller's `if (text != null)`
        skips the spawn entirely (Ovicopter.cs:88)."""
        occupied = self._occupied(combat)
        return next((s for s in reversed(self.slots) if s not in occupied), None)

    @staticmethod
    def _occupied(combat) -> set:
        """The slot names `Enemies` currently holds.

        Both free-slot queries scan `CombatState.Enemies`, and a dead creature
        has already left that list (`CombatState.RemoveCreature`,
        CombatState.cs:287-290) — so its slot is free again for the next
        summon. The sim keeps corpses in `combat.enemies` instead of removing
        them, so the membership test is `is_removed_from_combat`, the same
        predicate `fabricator.py:55` and `queen.py:201` use for their own
        `Enemies` scans.
        """
        return {c.slot_name for c in combat.enemies
                if not c.is_removed_from_combat}

    @property
    def entry(self) -> str:
        """The game's ModelId.Entry (StringHelper.Slugify of the encounter
        class name — UPPER_SNAKE_CASE), used to seed the per-encounter monster-
        selection Rng (EncounterModel.GenerateMonstersWithSlots) and, through
        it, the pre-generated monster HP for the room.

        `id.upper()` recovers it for the 78 encounters whose sim id IS their
        class-name slug. It does NOT for the other nine, which is a wrong KEY
        into a faithful formula — every draw off the resulting stream
        disagrees with the game's from the first one. Those nine set
        `entry_slug` explicitly, and the sweep test asserts that no tenth
        appears: a sim id is only allowed to differ from a real C# encounter
        class slug when `entry_slug` supplies the real one.
        """
        return self.entry_slug or self.id.upper()

    def calculate_gold_proportion(self, combat) -> float:
        """`EncounterModel.CalculateGoldProportion` (EncounterModel.cs:373-376)
        — `1 - EscapedCreatures.Count / SpawnedEnemies.Count`, the share of the
        encounter that was killed rather than let go. `CombatRoom.OnCombatEnded`
        reads it once and `RewardsSet` scales the MONSTER gold range by it
        (RewardsSet.cs:225-227), skipping the reward entirely at 0.

        The two counts are deliberately different shapes and are ported that
        way: `EscapedCreatures` is a list of CREATURES
        (`CombatState.CreatureEscaped`, CombatState.cs:266-270), while
        `SpawnedEnemies` is deduplicated by canonical MonsterModel
        (`OnCreatureSpawned`, EncounterModel.cs:402-412) — so three Two-Tailed
        Rats count as ONE spawned enemy. The sim keeps every creature it ever
        added in `combat.enemies` (corpses and escapees included), which is
        what both counts read.
        """
        spawned = {type(e) for e in combat.enemies}
        if not spawned:
            return 1.0
        escaped = sum(1 for e in combat.enemies if e.escaped)
        return 1.0 - escaped / len(spawned)

    def seat_in_slots(self, monsters: list[Monster]) -> list[Monster]:
        """Apply `monster_slots` positionally.

        `GenerateMonstersWithSlots` hands CombatState.CreateCreature the slot
        alongside the model, so a seeded monster arrives already seated.

        `CombatState.__init__` applies this to whatever `create_monsters`
        returns, so the seventeen encounters that OVERRIDE `create_monsters`
        get seated too — a summon that consults the row
        (`get_next_slot`/`last_free_slot`) reads occupancy off exactly these
        `slot_name`s, and an override that quietly skipped the seating would
        make the row look empty. Idempotent, so the base implementation below
        may also call it.
        """
        for monster, slot in zip(monsters, self.monster_slots):
            monster.slot_name = slot
        return monsters

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Fixed composition draws no RNG, so the parity selection_rng (when
        # present) is simply unused here.
        return self.seat_in_slots([cls(hooks, rng) for cls in self.monster_classes])
