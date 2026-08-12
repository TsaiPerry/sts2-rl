"""CombatState — the top-level combat driver and turn loop.

Owns the player, the enemy list, the shared RNG, the HookSystem, and the
CombatHistory, and wires them together at construction. Exposes the player-
facing API — `play_card` / `auto_play_card` / `use_potion` / `end_turn` /
`select_cards` / `valid_actions` — and runs the turn structure documented in
CLAUDE.md (player turn-end → turn-end-in-hand cards → discard → per-enemy
turns → side-end → next player turn), ending combat when the player dies or
every non-minion enemy is gone.

Also defines `CombatCtx`, the lightweight per-execution context handed to cards
and Cmds during resolution, and the `Phase` / `CombatResult` value types.
"""
from __future__ import annotations

import random
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Optional, TYPE_CHECKING

from .cards import Card, CardRarity, CardType, make_card, TargetType
from .cmds import DamageCmd
from .history import CombatHistory
from .hooks import HookSystem
from .monsters import Encounter, Monster, MoveType, FUZZY_WURM_ENCOUNTER
from .monsters.base import IntentHistoryEntry, MAX_INTENT_HISTORY, intent_flags
from .monsters.state_machine import STUN_STATE_ID
from .player import PlayerCombatState
from .potions import Potion
from .turn_phase import PlayerTurnPhase

if TYPE_CHECKING:
    from .relics import Relic
    from .rewards import RewardExtra
    from .rng import RunRngSet


class Phase(Enum):
    PLAYER_TURN = "player_turn"
    COMBAT_OVER = "combat_over"


@dataclass
class CombatResult:
    player_won: bool
    turns_taken: int


# CardRarity.cs's declaration order (CardSelectCmd.cs:406 `orderby c.Rarity,
# c.Id` sorts on this ordinal: None=0, Basic=1, Common=2, Uncommon=3, Rare=4,
# Ancient=5, Event=6, Token=7, Status=8, Curse=9, Quest=10). The sim's
# CardRarity enum (cards/base.py) lists members in a DIFFERENT order (EVENT
# after CURSE, not before TOKEN), so this maps explicitly to C#'s ordinal
# rather than reusing Python declaration order. CardRarity.None has no sim
# analogue — every combat card is one of these ten.
_CS_RARITY_ORDER = {
    CardRarity.BASIC: 1,
    CardRarity.COMMON: 2,
    CardRarity.UNCOMMON: 3,
    CardRarity.RARE: 4,
    CardRarity.ANCIENT: 5,
    CardRarity.EVENT: 6,
    CardRarity.TOKEN: 7,
    CardRarity.STATUS: 8,
    CardRarity.CURSE: 9,
    CardRarity.QUEST: 10,
}


def _sample_without_replacement(rng, population: list, k: int) -> list:
    """Pick k distinct items from population via repeated `.choice()` draws.

    No C# analogue: real `CardSelectCmd` never falls back to randomness when
    no Selector is installed — it always shows a UI screen or waits on the
    network (CardSelectCmd.cs). This whole branch is a sim-only
    headless-completion path for a parity-mode combat that (unusually) has no
    card_selector installed. `.choice()` is the one primitive both
    `random.Random` (legacy) and `GameRandomAdapter` (parity) provide, so this
    works for either — `random.Random.sample` is NOT used here because
    `GameRandomAdapter` deliberately does not implement it (rng.py:276-296:
    only methods that mirror a verified game primitive are added)."""
    pool = list(population)
    picked = []
    for _ in range(k):
        item = rng.choice(pool)
        pool.remove(item)
        picked.append(item)
    return picked


@dataclass
class CombatCtx:
    """Lightweight context passed to cards and Cmds during execution."""
    combat: CombatState
    player: PlayerCombatState
    enemies: list[Monster]
    hooks: HookSystem

    @property
    def enemy(self) -> Monster:
        """First living enemy; falls back to the first enemy if all are gone."""
        for e in self.enemies:
            if not e.is_gone:
                return e
        return self.enemies[0]

    def resolve_target(self, target_idx: int | None) -> Monster:
        """Return the indexed enemy if it is alive; otherwise the first living enemy."""
        if target_idx is not None and target_idx < len(self.enemies) and not self.enemies[target_idx].is_gone:
            return self.enemies[target_idx]
        return self.enemy

    @property
    def hittable_enemies(self) -> list[Monster]:
        """`ICombatState.HittableEnemies` — see `CombatState.hittable_enemies`."""
        return self.combat.hittable_enemies


class CombatState:
    PLAYER_MAX_HP = 80

    def __init__(
        self,
        starting_deck: list[Card] | None = None,
        rng: random.Random | None = None,
        rng_set: "RunRngSet | None" = None,
        encounter: Encounter | None = None,
        potions: list[Potion] | None = None,
        relics: list[Relic] | None = None,
        card_selector=None,
        max_hp: int | None = None,
        current_hp: int | None = None,
        room_type=None,
        max_potions: int | None = None,
        player_gold: int = 0,
        encounter_selection_rng=None,
        character=None,
        track_card_ids: bool = False,
        ascension: int = 0,
    ) -> None:
        # The character fighting this combat (CombatManager reaches it as
        # `Owner.Character`). In-combat card generation draws from
        # `character.card_pool`, so it has to be reachable from every card,
        # relic, power and potion — all of which hold a `combat` back-reference.
        # `RunState.create_combat` passes the run's; a bare CombatState (tests,
        # the combat-only envs) defaults to Ironclad, as it always has.
        from .characters import DEFAULT_CHARACTER, get_character

        self.character = get_character(
            character if character is not None else DEFAULT_CHARACTER
        )
        self._rng = rng or random.Random()
        # The run's serialized stream set (parity runs only). Kept so combat
        # content that must draw on a RAW game `Rng` — the potion factory's
        # NextFloat+NextItem pair (Alchemize) — can reach it.
        self.rng_set = rng_set
        from .combat_rng import CombatRng
        self.combat_rng = (
            CombatRng.parity(rng_set) if rng_set is not None
            else CombatRng.legacy(self._rng)
        )
        # The run-layer RoomType this combat happens in (Monster/Elite/Boss),
        # None for room-less combats (tests, the combat-only envs). Room-gated
        # relic effects read it (Booming Conch fires in Elite rooms only).
        self.room_type = room_type

        if starting_deck is None:
            starting_deck = [make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)]

        self.hooks = HookSystem()
        self.hooks.combat = self
        # Must be set before `create_monsters` below (and before any other
        # hook listener registration) — monster HP/move rolls read
        # `hooks.ascension` at construction time (asc_value), so setting it
        # after this constructor returns would silently leave every spawned
        # monster at ascension 0. See RunState.create_combat, which passes
        # the run's ascension in as this kwarg.
        self.hooks.ascension = ascension
        # PlayerCombatState.TurnNumber — bumped for EVERY player turn, extra
        # turns included (CombatManager.cs:1417). This is what turn-numbered
        # content reads: Horn Cleat, Captain's Wheel, Sparkling Rouge, Royal
        # Poison, Anchor.
        self.turn = 1
        # CombatState.RoundNumber (CombatState.cs:102, initialised to 1 at
        # :156) — bumped only on a NORMAL round (CombatManager.cs:1413), so an
        # extra player turn is still the same round. CombatHistory stamps every
        # entry with it (CombatHistory.cs:40-120), which is what makes "did X
        # happen this turn" survive an extra turn, and AbstractModel.cs:1125
        # tells content to pair AfterSideTurnStart "with a RoundNumber check".
        self.round_number = 1
        # Combat event log (mirrors CombatManager.History). Registered before
        # any other listener so entries exist by the time powers/cards react.
        self.history = CombatHistory(self)
        self.hooks.register(self.history)
        self.player = PlayerCombatState(
            max_hp if max_hp is not None else self.PLAYER_MAX_HP,
            starting_deck, self.combat_rng, self.hooks, potions=potions,
            max_potions=max_potions,
        )
        if current_hp is not None:
            # Runs enter combats with carried-over HP (RunState.create_combat).
            self.player.hp = min(current_hp, self.player.max_hp)
        # Cards are hook listeners for their whole combat lifetime (mirrors
        # CardModel being an AbstractModel), so cards like Drum of Battle can
        # react to events from any pile.
        for card in self.player.all_cards:
            card.reset_combat_state()
            card.combat = self
            self.hooks.register(card)
            # An affliction listens alongside its card too — C# adds it to the
            # walk between the card and the card's enchantment
            # (CombatState.cs:458-461), and AfflictionModel.cs:146 declares
            # ShouldReceiveCombatHooks. A deck card can arrive already
            # afflicted: `CardCmd.afflict` is the same command in and out of
            # combat and deliberately allows the out-of-combat case (see its
            # asymmetric IsEnding guard). hook_dispatch/G6.
            if card.affliction is not None:
                self.hooks.register(card.affliction)
            # Enchantments listen alongside their card (the game clones the
            # canonical enchantment into each combat with a fresh status).
            if card.enchantment is not None:
                card.enchantment.reset()
                card.enchantment.combat = self
                self.hooks.register(card.enchantment)
        # `NetCombatCardDb` (combat_card_db.py) — the replay harness's card
        # oracle, and THIS is the game's own instant for starting it:
        # `CombatManager.SetUpCombat` calls `NetCombatCardDb.Instance.
        # StartCombat` at CombatManager.cs:372, immediately after every
        # player's `PopulateCombatState` (:370) cloned the deck into the draw
        # pile and randomized it — which `PlayerCombatState.__init__` has just
        # finished doing — and BEFORE the `AddCreature` loop below, before
        # `Hook.BeforeCombatStart` and long before `StartTurn`'s opening draw.
        # Cards generated later are stamped AS THEY ARE ADDED
        # (`CardPileCmd._enter_combat`), never reconstructed afterwards.
        #
        # Off unless asked for: nothing in normal play or RL training reads a
        # card id, and the conformance runner is the only caller that does.
        self.card_db = None
        if track_card_ids:
            from .combat_card_db import CombatCardDb
            self.card_db = CombatCardDb(self)
        # `CombatState.Encounter` — kept because it is not just provenance:
        # `SortEnemiesBySlotName` reads `Encounter.Slots` to order the enemy list
        # (CombatState.cs:495-501) and the summoners read it to pick their slot.
        self.encounter: Encounter = encounter or FUZZY_WURM_ENCOUNTER
        self.enemies: list[Monster] = self.encounter.seat_in_slots(
            self.encounter.create_monsters(
                self.hooks, self._rng, encounter_selection_rng
            )
        )
        # Stable creature ids (CombatState.CombatId): the player is 0, initial
        # enemies get 1..N in creation order, mid-combat spawns continue the
        # counter (CreatureCmd.add). The recording targets cards by this id, so
        # it must survive enemy-list reordering (Ovicopter egg slots).
        self._net_id_counter = 1
        for _enemy in self.enemies:
            _enemy.net_id = self._net_id_counter
            self._net_id_counter += 1
        # R3: per-enemy displayed-intent history, keyed by net_id (NOT list
        # position — three encounters reorder a live enemy's slot mid-combat:
        # `cmds.py`'s `sort_enemies_by_slot_name` and `living_fog.py`'s
        # explicit insert index). A fresh dict per CombatState, so a new
        # combat/episode never inherits a previous one's history. See
        # `_record_intent_history` for the one place entries are appended.
        self._intent_history: dict[int, deque] = {}
        # Parity: monster max HP is a game RNG roll on the Niche stream, unique per
        # side where possible (Creature.SetUniqueMonsterHpValue, CombatState.cs:240).
        # Legacy mode keeps the monsters' own random.Random().randint roll untouched.
        # The Niche stream (monster unique-HP rolls); None in legacy mode. Held
        # so mid-combat spawns (Wrigglers, Axebot) can roll HP the same way the
        # initial enemies do — CreateCreature -> SetUniqueMonsterHpValue.
        self._niche = rng_set.niche if rng_set is not None else None
        if self._niche is not None:
            self._assign_parity_monster_hp(self.enemies, self._niche)
        # Relics are hook listeners for the whole combat (mirrors RelicModel :
        # AbstractModel with ShouldReceiveCombatHooks); attach() sets the
        # combat back-reference and registers them.
        self.relics: list[Relic] = list(relics or [])
        for relic in self.relics:
            relic.attach(self)
        # Belt potions are hook listeners too (CombatState.IterateHookListeners
        # walks each player's Powers, Relics, then PotionSlots) — that is how
        # Fairy in a Bottle's ShouldDie is consulted while it sits in the belt.
        # Potions procured mid-combat register in PlayerCombatState.add_potion.
        for _potion in self.player.held_potions:
            _potion.combat = self
            self.hooks.register(_potion)
        self.phase = Phase.PLAYER_TURN
        # Which side is currently acting ("player" / "enemy"); mirrors the
        # game's CombatState.CurrentSide (used by e.g. Inferno).
        self.current_side = "player"
        # `CombatManager.PlayersTakingExtraTurn` (_playersTakingExtraTurn).
        # Cleared and refilled in SwitchFromPlayerToEnemySide
        # (CombatManager.cs:1360-1373) and still populated while StartTurn runs
        # (:435/:439) and therefore while Hook.AfterSideTurnStart fires (:522) —
        # which is how content tells an EXTRA player turn from an ordinary one.
        # RampartPower.cs:23 is the first reader.
        self.players_taking_extra_turn: list = []
        # Pluggable in-combat card chooser (see select_cards); None = random.
        # Accepted as a constructor arg because turn-1 effects (Gambling Chip)
        # can request a selection during __init__, before callers could set it.
        self.card_selector = card_selector
        # Gold gained during combat (PlayerCmd.GainGold from Hand of Greed).
        # The run has the gold ledger, so this accumulates and
        # RunState.finish_combat credits it; standalone combats ignore it.
        self.gold_gained = 0
        # The player's gold as visible inside this combat: player_gold is the
        # run's balance at entry (set by RunState.create_combat; 0 for
        # standalone combats), and gold_stolen accumulates in-combat thefts
        # (Gremlin Merc's Thievery — PlayerCmd.LoseGold GoldLossType.Stolen).
        # finish_combat settles the ledger.
        self.player_gold = player_gold
        self.gold_stolen = 0
        # Gold voluntarily spent in combat (PlayerCmd.LoseGold with a normal
        # loss type — Seal of Gold's 5-gold-per-turn). Settled by
        # RunState.finish_combat like thefts, but kept separate so "stolen"
        # keeps its meaning.
        self.gold_spent = 0
        # Pending post-combat "extras": reward entries a combat (or combat
        # event) appends during the fight for the reward screen to surface
        # afterwards (mirrors CombatRoom.AddExtraReward accumulating a room's
        # ExtraRewards). RunState.finish_combat drains these into the run.
        # First consumer: Thieving Hopper's returned card (SwipePower).
        self.pending_reward_extras: list["RewardExtra"] = []
        # Run-deck cards a Thieving Hopper stole this combat, recorded
        # here rather than read back off the surviving SwipePower:
        # SwipePower is stripped on its owner's death like any other
        # power (Creature.RemoveAllPowersAfterDeath), so the power is
        # gone by the time RunState.finish_combat runs. C# does the
        # deck removal at STEAL time (SwipePower.cs:75) for the same
        # reason. RunState.finish_combat drains this.
        self.stolen_deck_origins: list["Card"] = []
        # id(combat card) -> the run-deck card it was deep-copied from; the
        # sim's analogue of CardModel.DeckVersion. Populated by
        # RunState.create_combat; empty for room-less/standalone combats
        # (which have no deck, like a card with DeckVersion == null).
        self.deck_card_origins: dict[int, "Card"] = {}
        self.result: Optional[CombatResult] = None
        # Cards offered by a "choose a card" screen (Skill Potion, Discovery,
        # …) awaiting the player's pick. The conformance driver resolves it from
        # the recording's `SelectCardFromScreen N`; legacy resolves it inline.
        self._pending_screen_cards: Optional[list["Card"]] = None
        # CombatManager._cardOrPotionEffectDepth (CombatManager.cs:310-338).
        # The sim has a single player, so one counter rather than a per-player
        # dict. See _card_or_potion_effect.
        self._card_or_potion_effect_depth = 0
        # CombatManager._inPlayerTurnSetup / _deferredEndTurnTransition
        # (CombatManager.cs:470-471, 702-714, 722-735). See
        # _start_player_turn.
        self._in_player_turn_setup = False
        self._deferred_end_turn_transition = None
        # CombatManager._pendingLoss (CombatManager.cs:945-965). See
        # lose_combat / _process_pending_loss.
        self._pending_loss = None

        # StartCombatInternal's per-creature AfterCreatureAdded loop
        # (CombatManager.cs:394-398), which runs BEFORE Hook.BeforeCombatStart
        # (:404) and is where every starting enemy's FIRST intent is rolled.
        for _enemy in list(self.enemies):
            self.after_creature_added(_enemy)

        self.hooks.on_combat_start()
        # CombatManager.StartCombat ends in StartTurn (CombatManager.cs:418),
        # so turn 1 runs the enemy-intent pass like every other player turn.
        # Nothing has performed a move yet, so it is a no-op — the enemies'
        # opening intents came from the AfterCreatureAdded loop above.
        self._roll_enemy_intents()
        self._start_player_turn()
        # CombatManager.cs:573 calls CheckWinCondition immediately after
        # SetupPlayerTurn. The sim checked after each enemy move, after the
        # enemy side and after the NEXT player turn's setup, but nothing
        # followed the combat-start setup — so a player killed during turn-1
        # setup by an on_combat_start / on_player_turn_start(ed) listener was
        # left in Phase.PLAYER_TURN at 0 HP with a legal action set.
        self._check_win_condition()

    @property
    def enemy(self) -> Monster:
        """First living enemy; falls back to the first enemy if all are gone."""
        for e in self.enemies:
            if not e.is_gone:
                return e
        return self.enemies[0]

    @property
    def hittable_enemies(self) -> list[Monster]:
        """`CombatState.HittableEnemies` (CombatState.cs:142) —
        `Enemies.Where(e => e.IsHittable).ToList()`.

        Every AoE and every random-enemy draw in the game reads THIS, not "the
        enemies that are not gone": `IsHittable` also consults
        `Hook.ShouldAllowHitting` (Creature.cs:285-299), so a creature that is
        alive but mid-revival (Illusion, Adaptable, Reattach) is not a
        candidate — and that matters twice over for the RNG sites, because the
        `CombatTargets` index is drawn against the list's LENGTH.
        """
        from .cmds import is_hittable
        return [e for e in self.enemies if is_hittable(self.hooks, e)]

    @property
    def card_pool(self) -> tuple[str, ...]:
        """The fighting character's CardPool (`Owner.Character.CardPool`).

        Every in-combat card generator — Stoke, Infernal Blade, Creative AI,
        Vexing Puzzlebox, the Attack/Skill/Power potions — draws from this, so
        on a non-Ironclad run they generate that character's cards."""
        return self.character.card_pool

    @property
    def potion_pool(self) -> tuple[tuple[str, str], ...]:
        """GetPotionOptions: the character's potion pool, then the shared one.

        What in-combat potion generation (Alchemize, Entropic Brew) draws
        from."""
        from .potion_pools import character_potion_pool

        return character_potion_pool(self.character)

    def owns_potion(self, potion_cls) -> bool:
        """Whether the fighting character can be offered `potion_cls`
        (`RunState.owns_potion`, for in-combat generation)."""
        return potion_cls.character in (None, self.character.id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _roll_parity_hp(creature, existing_hps, niche) -> int:
        """Port of Creature.SetUniqueMonsterHpValue for ONE enemy on the Niche
        stream: pick a HP from [min_hp, max_hp] not already used by a sibling
        (ascending candidate order == the game's Range().ToHashSet() iteration);
        if the range is exhausted, fall back to a plain range roll
        (game: rng.NextInt(min, max+1))."""
        # Read the *class* bounds, not creature.min_hp/max_hp: Monster.__init__
        # already overwrote the instance's max_hp with its own (legacy,
        # uncompared) random.Random().randint roll, so the instance attribute no
        # longer reflects the declared [min_hp, max_hp] range.
        cls = type(creature)
        lo, hi = cls.min_hp, cls.max_hp        # inclusive
        taken = set(existing_hps)
        candidates = [v for v in range(lo, hi + 1) if v not in taken]  # ascending
        if candidates:
            hp = candidates[niche.next_int_range(0, len(candidates))]
        else:
            hp = niche.next_int_range(lo, hi + 1)
        creature.hp = creature.max_hp = hp
        return hp

    @classmethod
    def _assign_parity_monster_hp(cls, enemies, niche) -> None:
        """Port of Creature.SetUniqueMonsterHpValue over each enemy in creation
        order (each excludes earlier siblings' HP, mirroring the incremental
        CreateCreature -> AddCreature loop)."""
        assigned: list[int] = []
        for e in enemies:
            assigned.append(cls._roll_parity_hp(e, assigned, niche))
        # MonsterModel.AfterAddedToRoom's HP fix-up used to run here. It has
        # moved to `after_creature_added`, the port of the C# hook that owns
        # it — this method is only the `CreateCreature` HP roll that precedes
        # it, and it does not run in legacy mode or for a mid-combat spawn,
        # where the fix-up must.

    def assign_parity_hp(self, creature) -> None:
        """Roll a mid-combat-spawned enemy's HP on the Niche stream, mirroring
        CombatState.CreateCreature calling SetUniqueMonsterHpValue against the
        creatures already on the enemy side (so its HP is unique vs current
        siblings). No-op in legacy mode (no Niche stream)."""
        if self._niche is None:
            return
        existing = [e.max_hp for e in self.enemies]
        self._roll_parity_hp(creature, existing, self._niche)

    def _ctx(self) -> CombatCtx:
        return CombatCtx(self, self.player, self.enemies, self.hooks)

    def _all_enemies_dead(self) -> bool:
        # Minions (Kin Followers, Eye With Teeth) are secondary enemies: combat
        # is won once every primary enemy is dead or escaped, even if minions
        # survive.
        primaries = [e for e in self.enemies if "minion" not in e.powers]
        if not all(e.is_gone for e in (primaries or self.enemies)):
            return False
        # CombatManager.cs:196 — the last gate before the combat is won: a
        # power may hold the fight open around a creature that is dead at 0 HP
        # and about to revive (AdaptablePower, InfestedPower).
        return not self.hooks.should_stop_combat_from_ending()

    def after_creature_added(self, creature) -> None:
        """`CombatManager.AfterCreatureAdded` (CombatManager.cs:858-867):

            await creature.AfterAddedToRoom();
            if (creature.IsEnemy && _state.CurrentSide == CombatSide.Player)
                creature.Monster.RollMove(_state.Players.Select(p => p.Creature));

        **The side gate is the whole point.** A creature summoned during the
        ENEMY side gets no opening roll: it keeps `MonsterModel.NextMove`'s
        initial `new MoveState()` (UNSET_MOVE) and is first rolled by the next
        player-turn-start pass, at its position in the enemy list. The sim
        rolled unconditionally in `MachineMonster.__init__`, which put the draw
        at spawn time instead — one MonsterAi draw in the wrong stream
        position, and, because the pass then skipped the spawn, the draws of
        the spawn and its already-acting siblings were swapped for the rest of
        the combat.

        Called from combat setup — `StartCombatInternal` loops
        `_state.Creatures` here, before `Hook.BeforeCombatStart`
        (CombatManager.cs:394-403) — and from `CreatureCmd.add`. C# walks
        every creature and gates on `IsEnemy`; the sim walks `self.enemies`,
        which is that gate. `Creature.AfterAddedToRoom`'s other half, the
        MaxHp fix-up, is `Monster.adjust_hp_after_added` and runs here, as its
        first statement does — `await creature.AfterAddedToRoom()`. It used to
        hang off `_assign_parity_monster_hp`, which meant it never ran in
        legacy mode and never ran for a mid-combat spawn at all; C# runs it on
        every creature in both cases, always after `CreateCreature`'s HP roll.
        """
        creature.adjust_hp_after_added(
            [o for o in self.enemies if o is not creature])
        if self.current_side == "player":
            self._prepare_for_next_turn(creature)

    @staticmethod
    def _prepare_for_next_turn(enemy) -> None:
        """`Creature.PrepareForNextTurn` -> `MonsterModel.RollMove` ->
        `MonsterMoveStateMachine.FindNextMoveState`, whose first guard is

            if (!CanTransitionAway || (!_performedFirstMove && IsMove)) return;

        (MonsterMoveStateMachine.cs:60-63) — so rolling a monster that has not
        yet PERFORMED a move returns its telegraphed one unchanged, without
        touching the Rng. Both callers of the roll go through here because both
        need that stickiness: the AfterCreatureAdded roll and the
        player-turn-start pass.

        `MachineMonster` has the guard inside its own machine, but the
        hand-rolled monsters do not — their `telegraph_next_move` advances
        unconditionally — which is what `Monster.performed_first_move` stands in
        for (monsters/base.py). `has_rolled_a_move` is the other half: a
        creature still on UNSET_MOVE has no telegraphed move for the guard to
        keep, so it must roll.
        """
        if not enemy.performed_first_move and enemy.has_rolled_a_move:
            return
        enemy.telegraph_next_move()

    def _roll_enemy_intents(self) -> None:
        """CombatManager.StartTurn's player-turn-start pass
        (CombatManager.cs:478-484):

            if (!isExtraPlayerTurn)
                foreach (Creature enemy in _state.Enemies)
                    enemy.PrepareForNextTurn(_state.PlayerCreatures);

        ONE pass over the enemy list, in list order, at the top of every
        player turn — not one roll tacked onto the end of each enemy's move.
        The distinction is observable in the MonsterAi stream: an enemy that
        did not act because it was stunned still rolls here (the game performs
        its synthetic STUNNED move, so the machine is free to transition),
        where per-move rolling skipped it and desynced the stream by one draw
        for the rest of the combat. An EXTRA player turn skips the pass
        entirely, and a mid-combat spawn's single roll stays where
        CombatManager.AfterCreatureAdded puts it (MachineMonster.__init__).

        `_state.Enemies` holds the creatures still in the combat, so a corpse
        combat kept (a withered Decimillipede segment) is included and a dead
        or escaped creature that was removed is not. The
        `performed_first_move` guard is FindNextMoveState's
        `!_performedFirstMove && _currentState.IsMove -> return`
        (MonsterMoveStateMachine.cs:60-63): until a monster has performed a
        move its telegraphed one is sticky.

        That guard does NOT cover a creature that has never been rolled at
        all — an enemy-side spawn, which `after_creature_added` leaves on
        UNSET_MOVE. C# calls `PrepareForNextTurn` on every enemy
        unconditionally and lets the machine decide, and for an un-rolled
        spawn `_currentState` is the machine's INITIAL state, so the
        `IsMove` half of the guard is whatever that state is rather than a
        telegraphed move. Skipping it here would strand the spawn on
        UNSET_MOVE for the whole combat.
        """
        for enemy in list(self.enemies):
            if enemy.is_gone and not enemy.retained_after_death:
                continue
            if enemy.performed_first_move:
                # The intent this enemy is about to have rerolled is exactly
                # the one that was displayed to the player for the turn that
                # just ended (`performed_first_move` is only True once the
                # enemy has actually acted on a rolled intent — see its own
                # docstring) — so THIS is the single per-turn point where a
                # displayed intent becomes settled history, right before it
                # is superseded. Recording anywhere inside `current_intent`
                # itself would fire on every read (including mid-turn reads
                # for the live observation) and record values never held for
                # a whole turn; recording after `_prepare_for_next_turn` would
                # record the NEW intent instead of the one just superseded.
                self._record_intent_history(enemy)
            self._prepare_for_next_turn(enemy)

    def _record_intent_history(self, enemy: Monster) -> None:
        """Append ``enemy``'s currently-displayed intent to its net_id-keyed
        R3 history ring buffer (``MAX_INTENT_HISTORY`` entries, most-recent
        first). See ``monsters.base.IntentHistoryEntry`` for why the preview
        numbers are captured now rather than derived later from a stored
        ``Intent``."""
        if enemy.net_id is None:
            return
        from .previews import preview_incoming_damage
        # `displayed_intent` is the snapshot `_perform_move` took right
        # before `take_turn` ran (see monsters/base.py's docstring). It is
        # None only when `take_turn` never ran this cycle (the stunned
        # branch whose current move isn't the synthetic STUN_STATE_ID move,
        # `_run_enemy_turns`'s `elif enemy.stunned:` arm) — in that case
        # nothing mutated the monster's move-key state, so a live read is
        # exactly the displayed value.
        intent = (
            enemy.displayed_intent if enemy.displayed_intent is not None
            else enemy.current_intent
        )
        preview = preview_incoming_damage(self, enemy, intent)
        entry = IntentHistoryEntry(
            flags=intent_flags(intent, enemy.stunned),
            per_hit=preview.per_hit if preview is not None else None,
            hits=preview.hits if preview is not None else None,
            total=preview.total if preview is not None else None,
            status_count=(
                intent.status_count if intent.has(MoveType.STATUS_CARD) else None
            ),
        )
        buf = self._intent_history.get(enemy.net_id)
        if buf is None:
            buf = deque(maxlen=MAX_INTENT_HISTORY)
            self._intent_history[enemy.net_id] = buf
        buf.appendleft(entry)

    def _execute_enemy_turn(self) -> None:
        self.current_side = "enemy"
        try:
            self._run_enemy_turns()
        finally:
            self.current_side = "player"

    def _side_participants(self) -> list:
        """`_state.CreaturesOnCurrentSide.ToList()` for the enemy side
        (CombatManager.cs:444, :1250) — a SNAPSHOT, taken once and reused by
        every pass of that phase, so a creature removed part-way through still
        gets the rest of the passes it was captured for."""
        return [e for e in self.enemies
                if not (e.is_gone and not e.retained_after_death)]

    def _perform_move(self, enemy) -> None:
        """`MonsterModel.PerformMove` (MonsterModel.cs:434-453) around the
        move itself.

        Two lines of it are load-bearing outside the visuals: `IsPerformingMove`
        is raised at :440 and dropped at :447, and `CreatureCmd.cs:527` refuses
        the `combatState.RemoveCreature` half of the death removal while it is
        raised — so a monster that dies in the middle of its own move keeps its
        `Creature.CombatState` back-pointer, and therefore keeps receiving
        hooks (`Contains`' MonsterModel arm, CombatState.cs:585), until the
        move returns. `PerformMove`'s tail (:448-451) then completes the
        deferred removal. `retained_after_death` is the sim's cached answer to
        the same `ShouldCreatureBeRemovedFromCombatAfterDeath` consultation
        :449 re-runs, so it is read rather than re-dispatched.
        """
        enemy.is_performing_move = True
        # Snapshot the intent as displayed BEFORE `take_turn` can mutate any
        # move-key state it drives itself (hand-rolled monsters advance their
        # own state inside `take_turn`; see `Monster.displayed_intent`'s
        # docstring in monsters/base.py). `_record_intent_history` reads this
        # instead of re-querying `current_intent` live at the next
        # player-turn start, after `take_turn` has already moved on.
        enemy.displayed_intent = enemy.current_intent
        try:
            enemy.take_turn(self._ctx())
        finally:
            enemy.is_performing_move = False
            if enemy.is_dead and not enemy.retained_after_death:
                enemy.combat_removal_committed = True

    def _run_enemy_turns(self) -> None:
        # CombatManager.StartTurn runs THREE complete passes over the side's
        # captured participants before any of them acts, with one side-scoped
        # hook between the first and the second and one after the third — not
        # [clear, start, move, end] per enemy, which is what the sim used to do
        # (turn_structure gap G5). Every enemy power that looked like a
        # per-creature turn-start listener is really an implementation of one
        # of these side hooks: C# has no per-creature turn-start or turn-end
        # hook at all.
        #
        # CombatManager.cs:429 — the enemy side's StartTurn runs
        # SetPhaseForAllPlayers(PlayerTurnPhase.None) too; PlayerTurnPhase.cs:9
        # says in as many words that None is "used ... during the enemy's turn".
        self.player.turn_phase = PlayerTurnPhase.NONE

        # `SwitchSides` (CombatManager.cs:1420-1424) -> `Creature.OnSideSwitch`
        # -> `MonsterModel.OnSideSwitch` (MonsterModel.cs:479-483): every
        # creature's SpawnedThisTurn is cleared on EVERY side switch, in BOTH
        # directions. `SpawnedThisTurn` has exactly one C# reader —
        # `Creature.TakeTurn`'s guard (Creature.cs:706-716), fired only from
        # THIS side's own move loop below — so clearing it once here,
        # immediately before that loop's snapshot is taken, reproduces the
        # same observable result as the full bidirectional dispatch: a
        # creature spawned later in this same pass (during the side-start
        # hooks just below — e.g. Poison killing an InfestedPower/StockPower/
        # SurprisePower owner, whose replacement joins mid-AfterSideTurnStart)
        # still carries the True `SetUpForCombat` set when `CreatureCmd.add`
        # added it, and correctly skips its move this turn; every creature
        # already on the board is False by the time the move loop reads it,
        # same as after a real `OnSideSwitch`. See monsters/base.py's
        # `spawned_this_turn` for the setter side (construction == "added").
        for enemy in self.enemies:
            enemy.spawned_this_turn = False

        starting = self._side_participants()

        # Pass 1: Creature.BeforeTurnStart (CombatManager.cs:449-455) is the
        # `power.AmountOnTurnStart = power.Amount` snapshot (Creature.cs:
        # 673-679) — see `Creature.snapshot_powers_on_turn_start`. None of the
        # three C# readers (DrawCardsNextTurn, HelloWorld, SummonNextTurn) is
        # enemy-side content, so this pass has no observable enemy-side effect
        # today; it is still modelled for the same reason C# still runs it.
        for enemy in starting:
            enemy.snapshot_powers_on_turn_start()

        # Hook.BeforeSideTurnStart — ONCE for the side (:458).
        self.hooks.before_enemy_side_start()

        # Pass 2: Creature.AfterTurnStart -> ClearBlock, every participant
        # (:492-499).
        for enemy in starting:
            preventer: list = []
            if self.hooks.should_clear_block(enemy, preventer):
                enemy.block = 0
            else:
                self.hooks.after_preventing_block_clear(preventer, enemy)

        # Pass 3: Hook.AfterBlockCleared, every participant (:500-507),
        # UNCONDITIONALLY — the sim once gated the event on `enemy.block > 0`,
        # which the game does not.
        for enemy in starting:
            self.hooks.on_block_cleared(enemy)

        # Hook.AfterSideTurnStart — ONCE for the side (:522), then its `_late`
        # pass. Poison, Demon Form, Slow and the Plating decay resolve for
        # EVERY enemy here, before the first one moves.
        self.hooks.after_enemy_side_start()

        # CombatManager.cs:598 — CheckWinCondition guards the whole of
        # ExecuteEnemyTurn, so a side-start hook that killed the last enemy (or
        # the player) ends the combat before any move.
        self._check_win_condition()
        if self.phase == Phase.COMBAT_OVER:
            return

        # ExecuteEnemyTurn (:1072-1090) — the moves.
        for enemy in list(self.enemies):
            # ExecuteEnemyTurn iterates every creature still IN the combat
            # (_state.ContainsCreature) and Creature.TakeTurn has no IsDead
            # guard, so a corpse the combat retained (a withered Decimillipede
            # segment) keeps taking turns — that is how it reaches REATTACH.
            if enemy.is_gone and not enemy.retained_after_death:
                continue

            # Execute the enemy's move. A stunned creature's "skipped" turn is
            # not really skipped in C#: Creature.StunInternal
            # (Creature.cs:524-544) REPLACED its move with the synthetic
            # STUNNED MoveState, and MonsterModel.PerformMove performs that one
            # like any other — MoveState.PerformMove then
            # MoveStateMachine.OnMovePerformed. Performing it is what lifts the
            # stun's MustPerformOnceBeforeTransitioning pin so the next
            # player-turn-start roll can transition STUNNED -> the deferred
            # move (and re-log it). Turn-start and turn-end effects like Poison
            # fire on a stunned turn either way.
            if enemy.spawned_this_turn:
                # Creature.TakeTurn's guard (Creature.cs:706-716): a creature
                # that joined the fight THIS enemy turn (SpawnedThisTurn still
                # True — see the clear at the top of this method) never
                # reaches PerformMove at all, so MoveStateMachine.
                # OnMovePerformed never fires either — `performed_first_move`
                # stays False, keeping its telegraph (or UNSET_MOVE) sticky
                # for the next player-turn-start roll.
                pass
            elif enemy.stunned:
                # Snapshot the displayed intent BEFORE clearing the flag: for
                # a hand-rolled monster whose stun is its own `stunned`-gated
                # `current_intent` (Wriggler's spawn stun — not the synthetic
                # STUN_STATE move), `take_turn` never runs this cycle, so
                # without this the next roll's `_record_intent_history`
                # live-read fallback sees the POST-WAKE next move and the
                # history row records an intent that was never displayed
                # (89U (0,15): sim rows read the turn-4 attack/buff where the
                # game showed — and both live rows agreed on — stun all of
                # turn 3).
                enemy.displayed_intent = enemy.current_intent
                enemy.stunned = False
                move = getattr(enemy, "_current_move", None)
                if move is not None and move.id == STUN_STATE_ID:
                    self._perform_move(enemy)
                # MonsterModel.PerformMove -> MoveStateMachine.OnMovePerformed:
                # from here on the monster's telegraphed move is no longer
                # sticky, so the player-turn-start pass rolls it.
                enemy.performed_first_move = True
            else:
                self._perform_move(enemy)
                enemy.performed_first_move = True
            if self.player.is_dead:
                self.phase = Phase.COMBAT_OVER
                self.result = CombatResult(player_won=False, turns_taken=self.turn)
                return
            if self._all_enemies_dead():
                self._end_combat(player_won=True)
                return

        # EndEnemyTurnInternal (CombatManager.cs:1248-1257): Hook.BeforeTurnEnd,
        # the players' EndOfTurnCleanup, then Hook.AfterTurnEnd — each ONCE for
        # the whole side. Regen, Ritual, Hatch, Slumber, Escape Artist, Asleep
        # and the Battleworn Dummy's time limit are AfterSideTurnEnd
        # implementations and resolve on the second of the two.
        if self.phase != Phase.COMBAT_OVER:
            self.hooks.before_enemy_side_end()
            # CombatManager.cs:1252-1255 — EndOfTurnCleanup runs for every
            # player BETWEEN the two side hooks, so a single-turn Retain or
            # cost modifier granted from a BeforeTurnEnd listener is already
            # gone by AfterTurnEnd. The second of its two sites.
            self.player.end_of_turn_cleanup()
            self.hooks.on_enemy_side_end()

    def _check_win_condition(self) -> None:
        """CombatManager.CheckWinCondition — RECOMPUTE whether the combat is
        over and end it if so.

        Distinct from reading `self.phase`: the sim's other three "checks"
        (the flag-reads around end_turn) only test the cached COMBAT_OVER
        value, so nothing recomputed the condition outside the enemy loop.
        """
        if self.phase == Phase.COMBAT_OVER:
            return
        # CombatManager.cs:1048 — the pending loss is tested FIRST, so it wins
        # a tie in which the player and the last enemy die together.
        if self._has_pending_loss:
            self._process_pending_loss()
        elif self._all_enemies_dead():
            self._end_combat_internal()

    def lose_combat(self) -> None:
        """CombatManager.LoseCombat (CombatManager.cs:945-951) — MARK the loss.

        :941-943 says why it is only a mark: "The actual loss processing
        happens at the next safe point (in CheckWinCondition) to avoid race
        conditions where effects try to run after IsInProgress is false."
        Called from CreatureCmd.Kill (CreatureCmd.cs:450-455) once every player
        is dead.
        """
        if self._pending_loss is None:
            self._pending_loss = True

    @property
    def _has_pending_loss(self) -> bool:
        """`_pendingLoss != null`. `player.is_dead` stands in for the deaths
        that reached the player through the damage pipeline rather than an
        explicit `lose_combat()`: C# routes every one of them through
        CreatureCmd.Kill, which calls LoseCombat, so the two are the same
        condition. `getattr` for the same __init__ window `is_ending` documents."""
        return getattr(self, "_pending_loss", None) is not None or self.player.is_dead

    def _process_pending_loss(self) -> None:
        """CombatManager.ProcessPendingLoss (CombatManager.cs:956-965).

        Clears the mark, drops IsInProgress and raises the CombatEnded event.
        It fires NO HOOK — not Hook.AfterCombatEnd, not Hook.AfterCombatVictory
        — and there is no revive. The sim used to fire its one combat-end hook
        on this path with `player_won=False`.
        """
        self._pending_loss = None
        self.phase = Phase.COMBAT_OVER
        self.player.turn_phase = PlayerTurnPhase.NONE
        self.result = CombatResult(player_won=False, turns_taken=self.turn)

    def _end_combat_internal(self) -> None:
        """CombatManager.EndCombatInternal (CombatManager.cs:970-1030) — the
        VICTORY path, in the game's order: IsInProgress false (:977),
        SetPhaseForAllPlayers(None) (:978), every player's
        ReviveBeforeCombatEnd (:986), Hook.AfterCombatEnd (:988), then
        Hook.AfterCombatVictory (:999)."""
        self.phase = Phase.COMBAT_OVER
        self.player.turn_phase = PlayerTurnPhase.NONE
        self.result = CombatResult(player_won=True, turns_taken=self.turn)
        # Player.ReviveBeforeCombatEnd (Player.cs:821-827): a dead player is
        # healed to 1 BEFORE the hooks, because (:816-819) "if the player is
        # still dead during HookBus.AfterCombatEnd, their relics will not be
        # subscribed to the HookBus, and relics which rely on AfterCombatEnd to
        # reset state will not be reset for the next combat."
        if self.player.is_dead:
            self.player.hp = 1
            # The revive is `CreatureCmd.Heal(Creature, 1)` (Player.cs:823-826),
            # and `Creature.HealInternal` (Creature.cs:477-485) calls
            # `Player?.ActivateHooks()` when the heal takes a dead creature back
            # above zero. That is the entire POINT of doing the revive here
            # rather than after the hooks — Player.cs:816-819 spells it out: a
            # still-dead player's relics "will not be subscribed to the HookBus,
            # and relics which rely on AfterCombatEnd to reset state will not be
            # reset for the next combat". Chosen Cheese and every future
            # AfterCombatEnd relic reads through this flag now.
            self.player.is_active_for_hooks = True
        self.hooks.on_combat_end()
        self.hooks.on_combat_victory()

    def _end_combat(self, player_won: bool) -> None:
        """The two CheckWinCondition exits, by outcome. Kept as one entry point
        because most callers are statements of fact ("this fight is won now"),
        but the two paths share nothing beyond setting the phase."""
        if player_won:
            self._end_combat_internal()
        else:
            self._process_pending_loss()

    def _process_turn_end_cards(self) -> None:
        """Mirror DoTurnEnd: exhaust ethereal cards, then fire turn-end-in-hand effects."""
        ctx = self._ctx()

        # Ethereal cards with no turn-end effect exhaust immediately.
        for card in [c for c in self.player.hand if c.is_ethereal and not c.has_turn_end_in_hand_effect]:
            if self.hooks.should_ethereal_trigger(card):
                self.player.hand.remove(card)
                self.player.exhaust_pile.append(card)
                # CombatManager.cs:1240 — one of the only two
                # `causedByEthereal: true` sites in the game.
                self.hooks.on_card_exhausted(card, caused_by_ethereal=True)

        # Cards with a turn-end effect: fire the effect, then exhaust or discard.
        for card in [c for c in self.player.hand if c.has_turn_end_in_hand_effect]:
            # `CardModel.OnTurnEndInHandWrapper` (CardModel.cs:1682-1698) opens
            # with `await CardPileCmd.Add(this, PileType.Play)` (:1684) and its
            # own doc comment says so at :1673 ("While this method is being
            # run, this card will be in the Play pile"). The sim left the card
            # in NO pile for the duration of the effect, so a sweep over
            # `AllCards` could not see it and a reshuffle the effect triggered
            # behaved the same only by accident.
            self._add_to_play_pile(card)
            card.on_turn_end_in_hand(ctx)
            if self.player.is_dead:
                # CreatureCmd.Kill -> LoseCombat (CreatureCmd.cs:450-455) MARKS
                # the loss; EndPlayerTurnPhaseOneInternal's CheckWinCondition
                # (CombatManager.cs:1208) is the safe point that processes it.
                self.lose_combat()
                return
            # CardModel.cs:1690 — the wrapper decides on the RAW keyword.
            # `Hook.ShouldEtherealTrigger` was already consulted once this turn
            # end, in DoTurnEnd's partition above (CombatManager.cs:1233), and
            # only for the cards that had no turn-end effect. Re-consulting it
            # here would send a vetoed card to the discard pile where the game
            # exhausts it.
            # Both arms are pile-agnostic moves in C# (`CardCmd.Exhaust` at
            # :1692, `CardPileCmd.Add(this, Discard)` at :1696), so neither
            # assumes the effect left the card in Play.
            if card.is_ethereal:
                self.player.remove_from_current_pile(card)
                self.player.exhaust_pile.append(card)
                # CardModel.cs:1692 — the other one.
                self.hooks.on_card_exhausted(card, caused_by_ethereal=True)
            else:
                old_pile = self.player.remove_from_current_pile(card)
                self.player.discard_pile.append(card)
                self.hooks.after_card_changed_piles(card, old_pile, None)
                # No Hook.AfterCardDiscarded here. CardModel.cs:1696
                # (OnTurnEndInHandWrapper's non-Ethereal branch) calls
                # `CardPileCmd.Add(this, PileType.Discard...)` directly; the
                # hook's sole C# call site is CardCmd.cs:194, inside
                # DiscardAndDraw (Concentrate/Sly/Gambler's Brew/Gambling
                # Chip), which this method is not. Named-work filing
                # 2026-07-30 (no gap id) -- same class as tier-2 Task 10's
                # G11 premise reversal for discard_hand/FlushPlayerHand.
                # Removed by tier-2 Task 11, item G.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_card(self, hand_index: int, target_idx: int | None = None) -> bool:
        """Play the card at hand_index.

        For ANY_ENEMY cards, target_idx selects which enemy in self.enemies to
        attack; if omitted or out of range the first living enemy is used.
        SELF and ALL_ENEMIES cards ignore target_idx.

        Returns False if the action is invalid.
        """
        if self.phase != Phase.PLAYER_TURN:
            return False
        if hand_index < 0 or hand_index >= len(self.player.hand):
            return False

        card = self.player.hand[hand_index]
        if not card.is_playable:
            return False
        if not self.hooks.should_play_card(card):
            return False
        if card.energy_cost_x:
            # X-cost: spend ALL remaining energy; the card reads captured_x
            # (mirrors EnergyCost.CapturedXValue / ResolveEnergyXValue).
            # Listeners can raise the captured X without changing the energy
            # spent (ModifyXValue — Chemical X).
            actual_cost = self.player.energy
            card.captured_x = self.hooks.modify_x_value(card, actual_cost)
        else:
            actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
            if actual_cost > self.player.energy:
                return False

        self.player.energy -= actual_cost
        # PlayCardAction.cs:94-100 sets ResourceInfo.EnergySpent and
        # ResourceInfo.EnergyValue to the SAME number on the manual path.
        card.energy_value = actual_cost
        self.hooks.on_energy_spent(card, actual_cost)
        # The card is NOT taken out of the hand here: `CardPileCmd.
        # AddDuringManualCardPlay` (CardPileCmd.cs:669-670) is what removes it
        # from its current pile, and it is the first statement of
        # `OnPlayWrapper` (CardModel.cs:1875). The sim popped it early, which
        # is why `oldPile` was unavailable to the entry dispatch (G8) and why
        # `Hook.AfterEnergySpent` saw a hand the game still has the card in.
        self._resolve_card_play(card, target_idx)

        # CheckWinCondition (CombatManager.cs:1046-1059) — the loss
        # arm is tested FIRST, so it wins a simultaneous death.
        self._check_win_condition()

        return True

    def auto_play(self, card: Card, target_idx: int | None = None) -> bool:
        """Play a card outside the normal hand-index / energy flow (mirrors
        CardCmd.AutoPlay): used by content that plays a card for free
        (Imbued enchantment turn 1, Whispering Earring). The card is removed
        from the hand if present; energy is NOT spent here (callers that must
        pay spend it themselves). Returns False if not in the player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return False
        # Same as the manual path: the move out of the hand belongs to the
        # Play-pile entry inside `_resolve_card_play` (CardModel.cs:1879's
        # `CardPileCmd.Add(this, PileType.Play, ...)`).
        self._resolve_card_play(card, target_idx, is_auto_play=True)
        # CheckWinCondition (CombatManager.cs:1046-1059) — the loss
        # arm is tested FIRST, so it wins a simultaneous death.
        self._check_win_condition()
        return True

    def _result_pile_type_for_card_play(self, card: Card) -> str:
        """`CardModel.GetResultPileTypeForCardPlay` (CardModel.cs:2070-2082).

        `IsDupe || Type == Power -> PileType.None`; then
        `ExhaustOnNextPlay || Keywords.Contains(Exhaust) -> PileType.Exhaust`,
        CONSUMING `ExhaustOnNextPlay` on the spot (:2078); else Discard.

        The sim has no `IsDupe`: `CardModel.CreateDupe` (:2186-2196) is
        unported — `DuplicationPower` replays through the play COUNT, it does
        not mint a duplicate card — so the first leg reduces to the Power test
        and `getattr` keeps the citation literal for a later dupe port.
        """
        if getattr(card, "is_dupe", False) or card.card_type == CardType.POWER:
            return "none"
        if card.exhaust_on_next_play or card.exhausts:
            card.exhaust_on_next_play = False
            return "exhaust"
        return "discard"

    def _add_to_play_pile(self, card: Card) -> None:
        """The Play-pile ENTRY, shared by both wrappers.

        Manual: `CardPileCmd.AddDuringManualCardPlay` (CardPileCmd.cs:647-684)
        — capture `oldPile` (:659), `RemoveFromCurrentPile` (:669),
        `AddInternal` into Play (:670, a raw insert with no per-card hook),
        then ONE `Hook.AfterCardChangedPiles(..., oldPile?.Type ?? None,
        clonedBy: null)` at :683, AFTER the move.
        Auto: `CardPileCmd.Add(this, PileType.Play, Bottom, null, ...)`
        (CardModel.cs:1879), whose dispatch is CardPileCmd.cs:635 with the same
        `oldPile?.Type ?? PileType.None` and the same literal null `clonedBy`.

        Both shapes are the same three statements, which is why this is one
        method. seam/creature_card_cmds guard G8's last unwired site.

        Both refuse once the combat is over or ending, and by the same
        predicate: `AddDuringManualCardPlay` returns on `IsOverOrEnding`
        outright (:649-652), while `Add`'s two guards — `IsCombatPile &&
        IsEnding -> success:false` (:312-319) and `IsCombatPile &&
        !IsInProgress -> return` (:398-401) — are together the same thing. The
        card then stays where it was, and every caller's Play gate turns the
        rest of its own work into a no-op for it.
        """
        if self.is_over_or_ending:
            return
        old_pile = self.player.remove_from_current_pile(card)
        self.player.play_pile.append(card)
        self.hooks.after_card_changed_piles(card, old_pile, None)

    def _resolve_card_play(self, card: Card, target_idx: int | None,
                           is_auto_play: bool = False) -> None:
        """`CardModel.OnPlayWrapper` (CardModel.cs:1867-2005): the card moves
        into `PileType.Play`, its result pile is decided, the play-count loop
        runs, and the card leaves Play through a switch that is GATED on it
        still being there.

        The card must still be in whichever pile it is being played FROM —
        this method performs the move, exactly as the wrapper's first
        statement does.
        """
        # :1875 (manual) / :1879 (auto) — into Play, before anything else.
        self._add_to_play_pile(card)

        # Resolve the single creature this play targeted (mirrors CardPlay.
        # Target): only ANY_ENEMY cards resolve to one enemy up front; AoE/
        # self/random-target cards have no single target (Target stays None
        # in the game too). Consulted by SurroundedPower to flip Kaiser Crab
        # facing on any targeted card play, not just damaging ones.
        played_target = (
            self._ctx().resolve_target(target_idx)
            if card.target_type == TargetType.ANY_ENEMY
            else None
        )
        # :1890 — `Hook.ModifyCardPlayResultPileTypeAndPosition` is consulted
        # ONCE, with `GetResultPileTypeForCardPlay()` as its `defaultPileType`
        # argument, and it is consulted BEFORE `GeneratePlayCount` (:1895) and
        # before any CardPlayStarted entry for this card exists. Nostalgia
        # counts CardPlaysStarted this turn, so it must not see the play it is
        # deciding about. The MOVE still happens after the loop, at :1976-1991.
        #
        # The sim used to ask for the play count FIRST and to pass the literal
        # "discard" for every card, which forced Rebound to re-derive the
        # Exhaust seed itself (see ReboundPower's docstring) and hid the
        # Exhaust/None arms from every listener.
        result_pile = self.hooks.modify_card_play_result_pile(
            card, self._result_pile_type_for_card_play(card))
        # BaseReplayCount (Hidden Gem) seeds the play count; enchantment
        # replays (Spiral/Glam) stack on top via the hook.
        play_count = self.hooks.modify_card_play_count(
            card, self.enemy, 1 + card.base_replay_count
        )
        # :1896-1899 — `if (Owner.Creature.IsDead) return;`, BETWEEN
        # GeneratePlayCount and BeginCardOrPotionEffect. A player already dead
        # here never reaches BeforeCardPlayed, and the return skips the exit
        # switch, so the card stays in Play.
        if self.player.is_dead:
            return
        # Attack plays are bracketed by the attack-command boundary (mirrors
        # AttackCommand firing BeforeAttack/AfterAttack) so "next attack"
        # powers on the player (Vigor from Akabeko) consume their stacks after
        # one full multi-hit attack.
        is_attack = card.card_type == CardType.ATTACK
        # CardModel.cs:1904-1965 builds a FRESH CardPlay each iteration
        # (PlayIndex = i, :1919-1928) and fires Hook.BeforeCardPlayed (:1929)
        # AND Hook.AfterCardPlayed (:1959) INSIDE the loop. The sim fired each
        # once per logical play, so a Throwing-Axe-doubled Strike advanced Pen
        # Nib's counter by 1 where the game advances it by 2 — from the first
        # combat of a run, the two engines doubled a different attack.
        # CombatManager.BeginCardOrPotionEffect (CardModel.cs:1901) wraps
        # the whole play-count loop and is released in a `finally`
        # (:1967-1970), so the hand-empty check below sees a settled hand.
        #
        # `_playing_card` names the card whose wrapper is on the stack. It is
        # SAVED and RESTORED, not just cleared: a card whose OnPlay auto-plays
        # another card (Cascade) nests, and the old unconditional
        # `_playing_card = None` at the tail wiped the outer card's mark for
        # the rest of its own play.
        previous_playing = self.player._playing_card
        self.player._playing_card = card
        try:
            self._play_count_loop(card, play_count, played_target, is_attack,
                                  target_idx, is_auto_play)
        finally:
            self.player._playing_card = previous_playing
        # Every `if (Owner.Creature.IsDead) return;` inside the wrapper
        # (CardModel.cs:1932, :1940, :1950, :1960) returns out of the WHOLE
        # method — past the exit switch (:1976-1991) and past CheckForEmptyHand
        # (:1992). The card is left in the Play pile; C# leaves it there too.
        if self.player.is_dead:
            return
        self._move_to_result_pile_after_play(card, result_pile)
        # CardModel.cs:1992 — the FIRST of CheckForEmptyHand's two callers, and
        # the one the sim never had. It runs after the result-pile move, so a
        # card that exhausted itself has already left the hand.
        self._check_for_empty_hand()

    def _play_count_loop(self, card: Card, play_count: int, played_target,
                         is_attack: bool, target_idx: int | None,
                         is_auto_play: bool) -> None:
        """CardModel.cs:1901-1970 — the play-count loop and the
        BeginCardOrPotionEffect bracket it runs inside."""
        with self._card_or_potion_effect():
            for play_index in range(play_count):
                card.current_play_index = play_index
                self.hooks.before_card_played(card, played_target)
                # CardModel.cs:1930 — `History.CardPlayStarted` sits between
                # Hook.BeforeCardPlayed (:1929) and `await OnPlay` (:1931), and
                # it is a DIRECT call, not a hook. Pushing it here is what lets
                # a card auto-played from inside this card's OnPlay see this
                # play already counted (Normality, Nostalgia).
                self.history.card_play_started(card, is_auto_play)
                if is_attack:
                    self.hooks.before_attack(self.player, card)
                if card.target_type == TargetType.ALL_ENEMIES and not card.handles_own_routing:
                    # Framework routes: call on_play once per living enemy.
                    for idx, e in enumerate(self.enemies):
                        if e.is_gone:
                            continue
                        card.on_play(self._ctx(), idx)
                        if self._all_enemies_dead() or self.player.is_dead:
                            break
                else:
                    # Card handles its own routing (or doesn't need enemy iteration).
                    card.on_play(self._ctx(), target_idx)
                if is_attack:
                    self.hooks.after_attack(self.player, card)
                # CardModel.cs:1932-1935 — `if (Owner.Creature.IsDead) return;`
                # IMMEDIATELY after `await OnPlay`, i.e. BEFORE the enchantment
                # leg. A card play that kills its own player stops here.
                if self.player.is_dead:
                    return
                # EnchantmentModel.OnPlay is a DIRECT in-loop call, not a hook
                # (CardModel.cs:1937-1945) — after the card's own OnPlay and before
                # Hook.AfterCardPlayed.
                if card.enchantment is not None:
                    card.enchantment.on_play(card, played_target)
                    # :1940-1943 — the same early return after the enchantment.
                    if self.player.is_dead:
                        return
                # (:1946-1955, `Affliction.OnPlay` and its own IsDead return,
                # has no sim counterpart: no ported affliction has an OnPlay.)
                # Hook.AfterCardPlayed, per iteration and gated on the combat still
                # being in progress (CardModel.cs:1957-1959).
                #
                # The gate is `IsInProgress`, NOT `IsOverOrEnding`: Hook.
                # AfterCardPlayed (Hook.cs:278-294) is one of the dispatchers that
                # deliberately BYPASS IterateCombatHookListeners, and Hook.cs:275-276
                # says why — "Dispatched directly, not through the
                # IterateCombatHookListeners guard: it completes resolution of the
                # card that caused the kill." IsInProgress stays true between the
                # killing blow and the teardown (it is cleared only from
                # CheckWinCondition, CombatManager.cs:1046-1059, which runs after the
                # whole play action), so C# DOES dispatch on the lethal iteration.
                # `is_over` is the sim's IsInProgress analogue; using
                # `is_over_or_ending` here suppressed every AfterCardPlayed listener
                # on the winning card play. Contrast Hook.BeforeCardPlayed
                # (Hook.cs:263-270), which IS gated and which the sim does not gate.
                if not self.is_over:
                    self.hooks.on_card_played(card, is_auto_play)
                    # :1960-1963 — the last of the four IsDead returns, right
                    # after Hook.AfterCardPlayed.
                    if self.player.is_dead:
                        return
                # A dead ENEMY does not end the Replay loop: a Throwing-Axe-
                # doubled card that kills on iteration 0 still runs iteration
                # 1, which is how the game's per-play counters (Tuning Fork's
                # run-scoped SkillsPlayed) reach 2. The sim also broke on
                # `_all_enemies_dead()`, so it reached 0.

    def remove_card_from_combat(self, card: Card) -> None:
        """`CardPileCmd.RemoveFromCombat` (CardPileCmd.cs:90-191) for one card:
        take it out of its combat pile (:129), dispatch
        `Hook.AfterCardChangedPiles` with the pile it just left and a literal
        null `clonedBy` (:188), then `RemoveFromState()` (:189).

        `RemoveFromState` (CardModel.cs:1604-1608) is the first leg of the
        CardModel `Contains` arm (CombatState.cs:593), so the card also stops
        being a hook listener; the sim unregisters it (and its riders) for the
        same reason. `Card.reset_combat_state` clears the flag next combat,
        mirroring `AfterCloned` (:1228).
        """
        old_pile = self.player.remove_from_current_pile(card)
        self.hooks.after_card_changed_piles(card, old_pile, None)
        card.has_been_removed_from_state = True
        for listener in (card, card.enchantment, card.affliction):
            if listener is None:
                continue
            try:
                self.hooks.unregister(listener)
            except ValueError:
                pass

    def _move_to_result_pile_after_play(self, card: Card,
                                        result_pile: str) -> None:
        """CardModel.cs:1976-1991 — the play's EXIT.

            CardPile? pile = Pile;
            if (pile != null && pile.Type == PileType.Play)
                switch (resultPileType) {
                  case None:    await CardPileCmd.RemoveFromCombat(this);
                  case Exhaust: await CardCmd.Exhaust(choiceContext, this);
                  default:      await CardPileCmd.Add(this, resultPileType,
                                                      resultPilePosition);
                }

        The GATE is the point: an effect that moved the card out of Play
        during its own OnPlay (a return-to-hand, a transform, an exhaust) OWNS
        it, and the exit does nothing. The sim's two exit legs used to be
        guarded on discard membership instead, which is the same gate spelled
        with the wrong pile and which silently stopped matching once the card
        stopped being parked in the discard.

        A played Power card takes the `None` arm, which is why it leaves
        `AllPiles` and stops being a listener (CombatState.cs:449-467). Dormant
        on today's content — none of the NINE hook-implementing card classes
        (Bolas, Clash, Drum of Battle, Enthralled, Howl from Beyond, Normality,
        Regret, Stomp, Thrumming Hatchet) is a Power — but it is also what
        keeps `HookSystem._ordered` on its fast path after the first Power card
        of a combat.

        TWO of the three arms carry a combat-ending refusal of their own, and
        the third carries none. That asymmetry is C#'s and it is the whole
        reason the killing blow's card is still lying in the Play pile when
        the fight ends:

        * `default:` is `CardPileCmd.Add`, refused for a COMBAT pile while
          `IsEnding` (CardPileCmd.cs:312-319, every result `success:false`) and
          while `!IsInProgress` (:398-401, an early `return results`) — both
          strictly BEFORE `RemoveFromCurrentPile` (:496) and `AddInternal`
          (:510), so a refused add leaves the card exactly where it was.
        * `case Exhaust:` is `CardCmd.Exhaust`, whose entire body is inside
          `if (!CombatManager.Instance.IsOverOrEnding)` (CardCmd.cs:239-245) —
          so the move, `History.CardExhausted` and `Hook.AfterCardExhausted`
          are skipped TOGETHER.
        * `case None:` is `CardPileCmd.RemoveFromCombat` (:102-191), which has
          no liveness gate at all. A Power played as the killing blow still
          leaves the state.

        `IsOverOrEnding` is `IsEnding || !IsInProgress`
        (CombatManager.cs:210-219) and the two `Add` guards are together
        exactly that, which is why both arms below read the same predicate.
        `IsEnding` (:180-201) is true from the instant the last primary enemy
        dies — inside the killing blow's own wrapper, long before
        `CheckWinCondition`. Downstream this is dormant (`BlockCmd`,
        `DrawCmd`, `DamageCmd` and the draw itself are each separately
        `IsOverOrEnding`-gated, which is exactly why C# can afford to put the
        gate one level up); what it changes is the card's final pile and two
        dispatches C# does not make. R5-review RV-2.
        """
        if card not in self.player.play_pile:
            return
        if result_pile == "none":
            # No gate: CardPileCmd.RemoveFromCombat (:102-191) has none.
            self.remove_card_from_combat(card)
            return
        if result_pile == "exhaust":
            # `CardCmd.Exhaust` (CardCmd.cs:237-246). Its `!IsOverOrEnding`
            # wrapper at :239 covers the whole body, so an ending combat
            # leaves the card in Play and fires no AfterCardExhausted — and
            # that gate lives in `ExhaustCmd.exhaust`, where C# puts it, so it
            # covers this arm and the thirteen other sim exhaust sites alike.
            # Its own `CardPileCmd.Add(card, PileType.Exhaust, ...)` (:242) is
            # an AfterCardChangedPiles site in C# too; the sim's `ExhaustCmd.
            # exhaust` does not dispatch it, uniformly at every exhaust site —
            # see the R5 report's finding on the Add site's remaining sim
            # entry points.
            from .cmds import ExhaustCmd
            ExhaustCmd.exhaust(self.hooks, self.player, card)
            return
        # `default:` — a full `CardPileCmd.Add(this, resultPileType,
        # resultPilePosition)`, which dispatches AfterCardChangedPiles at
        # CardPileCmd.cs:635 with oldPileType = Play. "draw_top" is the sim's
        # spelling of `(PileType.Draw, CardPilePosition.Top)`, the only
        # non-default (pile, position) pair any ported listener returns
        # (Nostalgia, Rebound).
        if self.is_over_or_ending:
            # :312-319 / :398-401, both before the move. Same predicate as
            # `_add_to_play_pile`'s entry refusal, and for the same reason.
            return
        self.player.play_pile.remove(card)
        if result_pile == "draw_top":
            self.player.draw_pile.append(card)   # end of list = top of pile
        else:
            self.player.discard_pile.append(card)
        self.hooks.after_card_changed_piles(card, "play", None)

    def sort_enemies_by_slot_name(self) -> None:
        """`CombatState.SortEnemiesBySlotName` (CombatState.cs:495-501) —
        `_enemies.Sort((a, b) => Slots.IndexOf(a.SlotName) -
        Slots.IndexOf(b.SlotName))`, a no-op when the encounter is null.

        A creature with no slot (or one not in the row, e.g. the `string.Empty`
        GetNextSlot hands back for a full row) gets IndexOf == -1 and sorts to the
        FRONT, exactly as in C#. Python's sort is stable and C#'s List.Sort is
        not, but every slot index here is distinct, so the comparator is a total
        order and the two agree.
        """
        encounter = self.encounter
        if encounter is None or not getattr(encounter, "slots", ()):
            return
        slots = list(encounter.slots)

        def key(creature) -> int:
            name = creature.slot_name
            return slots.index(name) if name in slots else -1

        self.enemies.sort(key=key)

    def _move_to_result_pile_without_playing(self, card: Card) -> None:
        """`CardCmd.MoveToResultPileWithoutPlaying` (CardCmd.cs:133-137) plus
        the model method it delegates to (CardModel.cs:2089-2107) — the
        destination of every card `CardCmd.AutoPlay` refuses to play.

            await CardPileCmd.Add(card, PileType.Play);      // CardCmd.cs:135
            await card.MoveToResultPileWithoutPlaying(...);  // :136

        and the model method is GATED the same way the played exit is:

            if (pile != null && pile.Type == PileType.Play)
                IsDupe                      -> RemoveFromCombat
                ExhaustOnNextPlay|Exhaust   -> CardCmd.Exhaust
                else                        -> Add(Discard)

        Two things the sim's version had wrong, both now fixed. (1) It never
        moved the card into Play, so the gate had nothing to test and the
        entry's `AfterCardChangedPiles` never fired. (2) It had no `IsDupe`
        arm. The doc comment at :2086-2087 names the ONE way this differs from
        the played path — "Power cards do not get sent to Limbo, and instead
        get sent to the discard" — which falls out of the None arm being
        `IsDupe` here where `GetResultPileTypeForCardPlay` also tests
        `Type == Power`. The sim has no dupes (see
        `_result_pile_type_for_card_play`), so the arm is expressible but
        unreachable.

        The Exhaust arm is how Havoc's `forceExhaust` reaches an UNPLAYABLE
        card: a Burn pulled off the draw pile is exhausted, not discarded.
        """
        self._add_to_play_pile(card)                     # CardCmd.cs:135
        if card not in self.player.play_pile:            # :2092's gate
            return
        if getattr(card, "is_dupe", False):              # :2094-2097
            self.remove_card_from_combat(card)
            return
        if card.exhaust_on_next_play or card.exhausts:   # :2098-2101
            card.exhaust_on_next_play = False
            from .cmds import ExhaustCmd
            ExhaustCmd.exhaust(self.hooks, self.player, card)
            return
        self.player.play_pile.remove(card)               # :2104 Add(Discard)
        self.player.discard_pile.append(card)
        self.hooks.after_card_changed_piles(card, "play", None)

    def auto_play_card(self, card: Card, target_idx: int | None = None,
                       auto_play_type: str = "default") -> None:
        """Play a card for free (mirrors CardCmd.AutoPlay): no energy is spent.

        The card is removed from whichever pile currently holds it. Unplayable
        or hook-blocked cards move to the discard pile without being played;
        ANY_ENEMY cards target a random living enemy when target_idx is
        omitted. The played card ends in its normal result pile.
        """
        if self.phase == Phase.COMBAT_OVER or self.player.is_dead:
            return
        # The card is NOT taken out of its pile here. `CardCmd.AutoPlay` only
        # pre-adds a PILE-LESS card (`if (card.Pile == null) CardPileCmd.Add(
        # card, PileType.Play)`, CardCmd.cs:114-116) — the real move is
        # `OnPlayWrapper`'s own `Add(this, PileType.Play)` (CardModel.cs:1879),
        # or, for a refused play, `MoveToResultPileWithoutPlaying`'s
        # (CardCmd.cs:135). Both are pile-agnostic, so the "e.g. Howl From
        # Beyond replays itself from the exhaust pile" case the old four-pile
        # scan existed for is covered by construction.
        if not card.is_playable or not self.hooks.should_play_card(card, auto_play=True):
            self._move_to_result_pile_without_playing(card)
            return
        if card.target_type == TargetType.ANY_ENEMY and target_idx is None:
            # CardCmd.cs:77 — `Rng.CombatTargets.NextItem(combatState.
            # HittableEnemies)`, which is CombatState.HittableEnemies
            # (CombatState.cs:142) and NOT "every enemy that is not gone": a
            # creature can be present and un-hittable (Illusion, Reattach), and
            # the roll must not offer it. The sim read `not e.is_gone` here even
            # though its own comment already named HittableEnemies.
            from .cmds import is_hittable
            hittable = [i for i, e in enumerate(self.enemies)
                        if is_hittable(self.hooks, e)]
            if not hittable:
                # `if (target == null) MoveToResultPileWithoutPlaying`
                # (CardCmd.cs:80-84) — the card is spent without being played.
                self._move_to_result_pile_without_playing(card)
                return
            target_idx = self.combat_rng.targets.choice(hittable)
        if card.energy_cost_x:
            # AutoPlay captures X from current energy without spending it.
            card.captured_x = self.hooks.modify_x_value(card, self.player.energy)
        # CardCmd.cs:123-128 — `EnergySpent = 0, EnergyValue =
        # card.EnergyCost.GetAmountToSpend()`. The two ResourceInfo fields DIVERGE
        # on this path and only on this path, which is the whole point of there
        # being two: an auto-played 2-cost card spends nothing and still counts as
        # a 2-cost play. `GetAmountToSpend` is the player's energy for an X-cost
        # card and `max(0, cost with all modifiers)` otherwise
        # (CardEnergyCost.cs:134-141).
        card.energy_value = (
            self.player.energy if card.energy_cost_x
            else max(0, self.hooks.modify_card_energy_cost(card, card.energy_cost)))
        # BeforeCardPlayed fires for auto-plays too (0 energy SPENT) — powers
        # like Free Attack consume their stacks here.
        self.hooks.on_energy_spent(card, 0)
        # CardCmd.cs:122 — Hook.BeforeCardAutoPlayed, right before
        # card.OnPlayWrapper (:130), i.e. strictly before the
        # before_card_played that _resolve_card_play fires below (tier-2
        # Task 11, item B; creature_card_cmds/step46, dormant). Target
        # resolution mirrors _resolve_card_play's played_target exactly:
        # only ANY_ENEMY cards resolve to a single creature.
        auto_play_target = (
            self._ctx().resolve_target(target_idx)
            if card.target_type == TargetType.ANY_ENEMY else None
        )
        self.hooks.before_card_auto_played(card, auto_play_target,
                                           auto_play_type)
        self._resolve_card_play(card, target_idx, is_auto_play=True)

        # CheckWinCondition (CombatManager.cs:1046-1059) — the loss
        # arm is tested FIRST, so it wins a simultaneous death.
        self._check_win_condition()

    def select_cards(
        self,
        purpose: str,
        candidates: list[Card],
        count: int = 1,
        min_select: int | None = None,
        is_draw_pile: bool = False,
        has_shortcut: bool = True,
    ) -> list[Card]:
        """In-combat card selection (mirrors CardSelectCmd's selection screens).

        purpose is a short label describing the choice ("upgrade", "exhaust",
        "from_discard", ...) so a policy can distinguish selection contexts.
        The choice is delegated to self.card_selector — a callable
        (purpose, candidates, count) -> list[Card] — when one is installed
        (by tests, the env, or an agent); otherwise up to count cards are
        picked uniformly at random with the combat RNG.

        `min_select` is CardSelectorPrefs.MinSelect, which the sim previously
        did not model at all: it clamped `count` and returned exactly that
        many. Ashwater and Gambler's Brew both build
        `CardSelectorPrefs(prompt, 0, 999999999)` and Gambling Chip the same,
        and `FromHand`'s auto-resolve shortcut is `list.Count <= MinSelect`
        (CardSelectCmd.cs:708-711) — false for any non-empty hand at MinSelect
        0, so the screen is always shown and confirming NONE is a first-class
        outcome. Defaults to `count`, i.e. the old exactly-N behaviour.

        This does NOT model a full CardSelectorPrefs/UI screen — MinSelect
        only goes as far as expressing the shortcut condition below and the
        selectorless range fallback already had. `RequireManualConfirmation`
        itself is never a caller-visible flag; it is derived exactly the way
        CardSelectorPrefs derives it (CardSelectorPrefs.cs:77): true whenever
        a caller passes a genuine `min_select` different from `count` (a real
        MinSelect..MaxSelect range), false when `min_select` is left at its
        default (MinSelect == MaxSelect == count, matching the
        `CardSelectorPrefs(prompt, exactCount)` constructor).

        `is_draw_pile` marks a candidate list pulled from the draw pile
        (`FromCombatPile(Draw, ...)` — SecretTechnique/SecretWeapon,
        DropletOfPrecognition): C# re-sorts it `orderby Rarity, Id`
        (CardSelectCmd.cs:403-408) before an installed Selector sees it, so an
        automated selector gets a canonical view instead of the true draw
        order. It affects only what `card_selector` is shown, not the
        shortcut's pile-order return (C#'s shortcut runs BEFORE the sort) nor
        the selectorless RNG fallback (C# has no selectorless path at all).

        `has_shortcut` defaults to True because the auto-select shortcut is
        shared by `FromSimpleGridForRewards`/`FromSimpleGrid`/`FromCombatPile`/
        `FromHand` — every C# entry point this method otherwise mirrors
        (Choices Paradox is `FromSimpleGrid`, so it keeps the default). It is
        NOT shared by `FromChooseACardScreen` (CardSelectCmd.cs:216-261 —
        Discovery/Splash/Quasar, the four generator potions, Toolbox,
        Knowledge Demon's curse pick): that method has no
        `CardSelectorPrefs`/shortcut at all — with a Selector installed it
        ALWAYS calls `Selector.GetSelectedCards(cards, 0, 1)` (hardcoded
        MinSelect 0, MaxSelect 1) regardless of candidate count, and with none
        installed it always shows the UI or waits on the network. Callers
        whose C# citation is `FromChooseACardScreen` must pass
        `has_shortcut=False`.
        """
        # CardSelectCmd's first guard: every C# selection screen returns an
        # empty list once the combat is over or ending (CardSelectCmd.cs:194-199,
        # 277-285, 382-394, 694-707). The sim implemented only the
        # 0-candidate arm.
        if self.is_over_or_ending:
            return []
        if not candidates:
            return []
        # C#'s auto-select shortcut (CardSelectCmd.cs:287-290, 396-399,
        # 708-711): `!RequireManualConfirmation && candidateCount <=
        # MinSelect` -> every candidate, in PILE ORDER, calling neither the
        # Selector nor drawing from any RNG. Checked BEFORE the Selector
        # branch below — C# short-circuits ahead of any UI/manual selection,
        # and this mirrors that placement exactly. Gated on `has_shortcut`:
        # `FromChooseACardScreen` (CardSelectCmd.cs:216-261) has no such
        # shortcut at all — see the has_shortcut docstring note above.
        require_manual_confirmation = min_select is not None and min_select != count
        shortcut_floor = count if min_select is None else min_select
        if (has_shortcut and not require_manual_confirmation
                and len(candidates) <= shortcut_floor):
            return list(candidates)
        count = min(count, len(candidates))
        floor = count if min_select is None else min(min_select, len(candidates))
        if count <= 0 and floor <= 0:
            return []
        if self.card_selector is not None:
            pool = list(candidates)
            if is_draw_pile:
                # CardSelectCmd.cs:403-408 — see the is_draw_pile docstring
                # note above. Stable sort: the only cards that can tie on
                # (rarity, id) are literal duplicates, indistinguishable to a
                # selector either way.
                pool.sort(key=lambda c: (_CS_RARITY_ORDER[c.rarity], c.id))
            chosen = list(self.card_selector(purpose, pool, count))[:count]
            return [c for c in chosen if c in candidates]
        # No C# path reaches here selectorless (CardSelectCmd always shows a
        # UI screen or waits on the network) — this is a sim-only headless
        # completion fallback. Parity mode moves it onto the named
        # `combat_rng.card_selection` stream; legacy keeps drawing from the
        # shared `self._rng` exactly as before (byte-for-byte unchanged —
        # `combat_rng.card_selection` in legacy mode is not used here on
        # purpose, to keep this an explicit branch rather than an incidental
        # alias).
        rng = self.combat_rng.card_selection if self.combat_rng.is_parity else self._rng
        if floor < count:
            # With a real minimum below the maximum the selectorless path must
            # be able to return fewer than `count` — including none at all.
            count = rng.randint(floor, count)
        if count <= 0:
            return []
        if self.combat_rng.is_parity:
            return _sample_without_replacement(rng, candidates, count)
        return rng.sample(candidates, count)

    def use_potion(self, slot: int, target_idx: int | None = None) -> bool:
        """Use the potion in the given slot. The slot is nulled, not removed
        — Player.cs's belt is a fixed-length `List<PotionModel?>`, and using
        a potion (DiscardPotionInternal) never shifts the other slots down.

        For targeted potions, target_idx selects the enemy (defaults to the
        first living enemy). Returns False if the action is invalid.
        """
        if self.phase != Phase.PLAYER_TURN:
            return False
        if slot < 0 or slot >= len(self.player.potions):
            return False
        potion = self.player.potions[slot]
        if potion is None:
            return False
        # PotionUsage.Automatic potions have no manual use (the game disables
        # the Use button, NPotionPopup.cs:131) — only their own hook fires them.
        if potion.automatic:
            return False
        # `PotionModel.PassesCustomUsabilityCheck` (PotionModel.cs:158-164),
        # the same gate `RunState.use_potion` consults. True for every potion
        # in combat today — Foul Potion, the source's only override, opens
        # with `if (CombatManager.Instance.IsInProgress) return true` — but
        # the check belongs at both call sites, as it is in the game.
        if not potion.passes_custom_usability_check(combat=self):
            return False

        # PotionModel.OnUseWrapper starts with RemoveBeforeUse: the slot is
        # nulled (and the potion stops listening) before the effect resolves.
        self.player.potions[slot] = None
        self.player.detach_potion(potion)
        ctx = self._ctx()
        target = ctx.resolve_target(target_idx) if potion.targeted else None
        # PotionModel.OnUseWrapper's order (PotionModel.cs:291-342):
        # :293 RemoveBeforeUse (above), :297 BeforePotionUsed, :327 OnUse,
        # :338 AfterPotionUsed, :340 CheckForEmptyHand.
        self.hooks.before_potion_used(potion, target)
        # PotionModel.cs:324-332 — OnUse is bracketed by
        # Begin/EndCardOrPotionEffect exactly as a card play is, and the
        # release is a `finally`.
        with self._card_or_potion_effect():
            potion.use(ctx, target)
        self.hooks.on_potion_used(potion, target)
        self._check_for_empty_hand()

        # CheckWinCondition (CombatManager.cs:1046-1059) — the loss
        # arm is tested FIRST, so it wins a simultaneous death.
        self._check_win_condition()
        return True

    def _check_for_empty_hand(self) -> None:
        """CombatManager.CheckForEmptyHand (CombatManager.cs:887-893).

        Two callers, and CombatManager.cs:869-883 is unusually explicit about
        why there are exactly two: "we manually check after a card is played,
        and after a potion is used, since these are the two ways a player can
        manually interact with combat state (besides ending turn, which should
        not trigger an empty hand check)". CardModel.cs:1992 and
        PotionModel.cs:340. The end-of-turn flush is EXCLUDED on purpose.

        The `!IsExecutingCardOrPotionEffect` clause is the same docstring's
        worked example: with Unceasing Top and Pommel Strike as the last card
        in hand, the hand is momentarily empty the instant the card moves to
        the Play pile, so an unguarded check would draw once there and once
        again after Pommel Strike's own draw.
        """
        if self.phase == Phase.COMBAT_OVER:
            return
        if self._card_or_potion_effect_depth > 0:
            return
        if not self.player.hand:
            self.hooks.on_hand_emptied(self.player)

    def _start_player_turn(self) -> None:
        """StartTurn's player-side branch (CombatManager.cs:462-587).

        The setup window is opened at :470 (`_inPlayerTurnSetup = true`, right
        after PlayerTurnPhase.Start) and closed by
        ReleaseDeferredEndTurnTransitionIfNeeded (:722-735), which :720 says
        "must be called on every exit path of the player-turn setup ... so a
        deferred transition is never dropped" — hence the `finally`.

        Inside the window an end-turn is STORED rather than run (:702-714),
        because a card auto-played during the AutoPrePlay phase can end the
        turn and the transition must not race the tail of StartTurn. The sim's
        start_turn is synchronous, so without this an end_turn re-entered from
        inside it would recurse (turn_structure N1).
        """
        # Creature.BeforeTurnStart (Creature.cs:673-679), from StartTurn's own
        # per-creature loop (CombatManager.cs:447-450) — strictly BEFORE
        # `_inPlayerTurnSetup` is engaged and before Hook.BeforeSideTurnStart,
        # so it runs here rather than inside `player.start_turn()`. Covers
        # every player-side StartTurn call, extra turns included, since this
        # method is their one shared entry point. See
        # `Creature.snapshot_powers_on_turn_start`.
        self.player.snapshot_powers_on_turn_start()
        self._in_player_turn_setup = True
        try:
            self.player.start_turn()
        finally:
            self._in_player_turn_setup = False
            deferred = self._deferred_end_turn_transition
            self._deferred_end_turn_transition = None
            if deferred is not None:
                deferred()

    @property
    def is_player_ready_to_end_turn(self) -> bool:
        """CombatManager.IsPlayerReadyToEndTurn — with one player,
        `AllPlayersReadyToEndTurn()` (CombatManager.cs:695) is satisfied by
        that player alone, so readiness and the deferral are the same instant.
        Read by WhisperingEarring.cs:63-66 to stop auto-playing."""
        return self._deferred_end_turn_transition is not None

    @contextmanager
    def _card_or_potion_effect(self):
        """CombatManager.BeginCardOrPotionEffect / EndCardOrPotionEffect
        (CombatManager.cs:321-338) — a NESTING DEPTH, not a flag, because an
        effect body can auto-play another card (a Sly card discarded mid-play)
        and the outer body must still be "executing" when the inner one
        returns. C# pairs them in a `finally`; so does this."""
        self._card_or_potion_effect_depth += 1
        try:
            yield
        finally:
            self._card_or_potion_effect_depth -= 1

    def offer_screen_selection(self, cards: list[Card]) -> None:
        """Present a choose-a-card screen (mirrors CardSelectCmd.FromChooseA-
        CardScreen). The cards are generated already; the pick is deferred to
        the recording's `SelectCardFromScreen` (driver) or resolved inline in
        legacy play."""
        self._pending_screen_cards = list(cards)

    def resolve_screen_selection(self, index: int | None) -> None:
        """Resolve a pending choose-a-card screen: add the chosen generated card
        to hand, free this turn (AddGeneratedCardToCombat). `index is None`
        (a `SelectCardFromScreen skip`) takes nothing, as the game's canSkip
        screens allow."""
        cards = self._pending_screen_cards
        self._pending_screen_cards = None
        if not cards or index is None or index >= len(cards):
            return
        from .cmds import CardPileCmd
        card = cards[index]
        card.set_free_this_turn()
        CardPileCmd.add_to_hand(self.hooks, self.player, card)

    def end_turn(self) -> None:
        """SetReadyToEndTurn (CombatManager.cs:686-715) — ready this player and,
        if that is everyone, run the transition off the player side.

        During the player-turn setup window the transition is DEFERRED rather
        than run (:702-714); see _start_player_turn.
        """
        if self.phase != Phase.PLAYER_TURN:
            return
        if self._in_player_turn_setup:
            self._deferred_end_turn_transition = self._end_turn_internal
            return
        self._end_turn_internal()

    def _end_turn_internal(self) -> None:
        """AfterAllPlayersReadyToEndTurn (CombatManager.cs:1259-1272) and what
        it drives: both end-turn phases, then the switch to the enemy side."""
        if self.phase != Phase.PLAYER_TURN:
            return

        # PlayerTurnPhase.AutoPostPlay (CombatManager.cs:1160-1176): the
        # end-of-turn auto-plays drain in their own phase, entered STRICTLY
        # before Hook.BeforeTurnEnd. :1165 sets AutoPostPlay, :1175 sets End
        # once the hook's context has completed — so everything from
        # Hook.BeforeTurnEnd (:1179) onward runs in End.
        self.player.turn_phase = PlayerTurnPhase.AUTO_POST_PLAY
        self.hooks.after_auto_post_play_phase_entered(self.player)
        self.player.turn_phase = PlayerTurnPhase.END
        if self.phase == Phase.COMBAT_OVER:
            return

        self.hooks.on_player_turn_end(self.player)
        # CombatManager.cs:1181 — `if (await CheckWinCondition()) return;`.
        # A RECOMPUTATION, not a cached-flag read: a BeforeTurnEnd listener can
        # kill the last enemy (or the player) without routing through
        # _end_combat, and DoTurnEnd must not run afterwards.
        self._check_win_condition()
        if self.phase == Phase.COMBAT_OVER:
            return
        self._process_turn_end_cards()
        # CombatManager.cs:1200-1206 — Hook.BeforeFlush fires per player,
        # after the DoTurnEnd loop above and before the CheckWinCondition
        # that closes EndPlayerTurnPhaseOneInternal below (tier-2 Task 11,
        # item D; turn_structure/step55, dormant).
        self.hooks.before_flush(self.player)
        # CombatManager.cs:1207-1208 — the check that closes
        # EndPlayerTurnPhaseOneInternal, so phase two (the flush) never runs.
        self._check_win_condition()
        if self.phase == Phase.COMBAT_OVER:
            return
        # FlushPlayerHand (CombatManager.cs:1327-1346) treats ShouldFlush ==
        # false as "every card is retained": cardsToFlush is empty and the
        # batched Add is skipped, but the TAIL still runs — Hook.AfterFlush and
        # PlayerCombatState.EndOfTurnCleanup. The sim guarded the whole thing,
        # so a retain effect suppressing the flush silently dropped Joss
        # Paper's deferred Ethereal-exhaust credit with it.
        self.player.discard_hand(flush=self.hooks.should_flush_hand())
        # Hook.AfterTurnEnd for the player side (CombatManager.cs:1307): after
        # DoTurnEnd and FlushPlayerHand, still on the player's block.
        self.hooks.after_player_turn_end(self.player)
        if self.phase == Phase.COMBAT_OVER:
            return
        if self._all_enemies_dead():
            self._end_combat(player_won=True)
            return

        # Hook.ShouldTakeExtraTurn is evaluated in SwitchFromPlayerToEnemySide
        # (CombatManager.cs:1360-1373) — AFTER both end-turn phases have run —
        # and skips only the ENEMY SIDE. Testing it at the top of end_turn
        # short-circuited the entire turn-end pipeline: with Pael's Eye held
        # and no card played, a full hook trace recorded should_take_extra_turn
        # and nothing else — no on_player_turn_end, no flush, no
        # after_player_turn_end, though the sim has dozens of listeners on them.
        # CombatManager.cs:1363 — `_playersTakingExtraTurn.Clear()` happens on
        # EVERY pass through the switch, before the hook is polled, so an
        # ordinary turn never sees a stale flag.
        self.players_taking_extra_turn = []
        if self.hooks.should_take_extra_turn(self.player):
            # :1364-1371 — the player joins the list BEFORE SwitchSides and the
            # list is still populated when StartTurn and its
            # Hook.AfterSideTurnStart run, which is what RampartPower reads.
            self.players_taking_extra_turn.append(self.player)
            self.hooks.on_extra_turn(self.player)
            # SwitchSides' extra-turn branch (CombatManager.cs:1406-1418) runs
            # IncrementTurnNumber ONLY: `RoundNumber++` is on the other arm.
            self.turn += 1
            # No _roll_enemy_intents here: CombatManager.cs:478 gates the pass
            # on `!isExtraPlayerTurn`, so an extra player turn faces the same
            # intents (and takes no MonsterAi draw).
            self._start_player_turn()
            self._check_win_condition()
            return

        self._execute_enemy_turn()

        # EndEnemyTurn (CombatManager.cs:828-837): EndEnemyTurnInternal, then
        # CheckWinCondition (:830), and only `if (!IsEnding)` does it switch
        # sides and start the fresh turn. The sim read the cached phase, so an
        # AfterTurnEnd listener that killed the last enemy still got a new
        # player turn handed out.
        self._check_win_condition()
        if not self.is_ending and self.phase != Phase.COMBAT_OVER:
            # The normal round: both counters (CombatManager.cs:1410-1418).
            self.turn += 1
            self.round_number += 1
            # The enemy-intent pass runs inside StartTurn, before the player's
            # own turn setup draws anything (CombatManager.cs:478-484 precedes
            # SetupPlayerTurn at :510-523).
            self._roll_enemy_intents()
            self._start_player_turn()
            # CheckWinCondition right after the player's turn setup /
            # auto-pre-play phase (CombatManager.cs:573). A turn-start effect
            # can land the killing blow (Inferno's burst, a Poison tick) or kill
            # the player, and the game ends the fight there rather than handing
            # back a turn with no living enemies.
            self._check_win_condition()

    def valid_actions(self) -> list[int]:
        """0 = end turn, 1+ = play card at hand index (action - 1)."""
        if self.phase != Phase.PLAYER_TURN:
            return []
        actions = [0]
        for i, card in enumerate(self.player.hand):
            if not card.is_playable:
                continue
            if not self.hooks.should_play_card(card):
                continue
            if card.energy_cost_x:
                # X-cost cards are always affordable (X may be 0).
                actions.append(i + 1)
                continue
            actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
            if actual_cost <= self.player.energy:
                actions.append(i + 1)
        return actions

    @property
    def is_over(self) -> bool:
        return self.phase == Phase.COMBAT_OVER

    @property
    def is_ending(self) -> bool:
        """CombatManager.IsEnding (CombatManager.cs:180-202).

        `IsInProgress && (a loss is pending || no primary enemy is alive &&
        nothing vetoes the end)`. The leading `if (!IsInProgress) return false`
        is why a combat that has ALREADY ended is not "ending": the commands
        guarded on `IsEnding` rather than `IsOverOrEnding` (PowerCmd.Apply,
        CardCmd.Transform, CardPileCmd.Add) therefore also let an
        OUT-OF-COMBAT call through, which is how the deck transformers and the
        event card-adds keep working.

        `getattr`, for the same reason the combat-over hook gate needs it: a
        monster's constructor applies its starting powers through PowerCmd
        while `CombatState.__init__` is still running, before `phase` is
        assigned. That window is C#'s `IsStarting`, where nothing has died yet
        and no command should be refused.
        """
        if getattr(self, "phase", None) in (None, Phase.COMBAT_OVER):
            return False
        return self._has_pending_loss or self._all_enemies_dead()

    @property
    def is_over_or_ending(self) -> bool:
        """CombatManager.IsOverOrEnding (CombatManager.cs:204-220).

        `IsOverOrEnding` is `IsEnding || !IsInProgress`, and `IsEnding`
        (CombatManager.cs:171-202) is "combat is in progress AND either a loss
        is pending or every primary enemy is dead with nothing vetoing the
        end". `is_over` alone is only the `!IsInProgress` half: the sim flips
        `Phase.COMBAT_OVER` inside `_end_combat`, which the card-play paths
        reach strictly after `_resolve_card_play` returns — so between the
        killing blow and the teardown C# considers the combat *ending* and the
        sim considered it live. `_all_enemies_dead` already carries
        `Hook.ShouldStopCombatFromEnding` (combat.py's `_all_enemies_dead`,
        mirroring CombatManager.cs:196), which is what holds a fight open
        around a creature that is dead at 0 HP and about to revive.

        Combat SETUP is exempt in C# (`!CombatManager.IsStarting`,
        Hook.cs:45-47, so the initial shuffle still reaches listeners); the sim
        has no setup phase in which every enemy is already dead, so there is
        nothing to exempt.
        """
        return getattr(self, "phase", None) == Phase.COMBAT_OVER or self.is_ending
