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
from dataclasses import dataclass
from enum import Enum
from typing import Optional, TYPE_CHECKING

from .cards import Card, CardType, make_card, TargetType
from .cmds import DamageCmd
from .history import CombatHistory
from .hooks import HookSystem
from .monsters import Encounter, Monster, FUZZY_WURM_ENCOUNTER
from .monsters.state_machine import STUN_STATE_ID
from .player import PlayerCombatState
from .potions import Potion

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
        self.turn = 1
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
            # Enchantments listen alongside their card (the game clones the
            # canonical enchantment into each combat with a fresh status).
            if card.enchantment is not None:
                card.enchantment.reset()
                card.enchantment.combat = self
                self.hooks.register(card.enchantment)
        self.enemies: list[Monster] = (encounter or FUZZY_WURM_ENCOUNTER).create_monsters(
            self.hooks, self._rng, encounter_selection_rng
        )
        # Stable creature ids (CombatState.CombatId): the player is 0, initial
        # enemies get 1..N in creation order, mid-combat spawns continue the
        # counter (CreatureCmd.add). The recording targets cards by this id, so
        # it must survive enemy-list reordering (Ovicopter egg slots).
        self._net_id_counter = 1
        for _enemy in self.enemies:
            _enemy.net_id = self._net_id_counter
            self._net_id_counter += 1
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

        self.hooks.on_combat_start()
        # CombatManager.StartCombat ends in StartTurn (CombatManager.cs:418),
        # so turn 1 runs the enemy-intent pass like every other player turn.
        # Nothing has performed a move yet, so it is a no-op — the enemies'
        # opening intents come from AfterCreatureAdded's roll.
        self._roll_enemy_intents()
        self.player.start_turn()
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
        # MonsterModel.AfterAddedToRoom fires per creature once it is on the
        # board, after its HP roll; the only porting monster reshapes MaxHp
        # (Decimillipede's even-and-unique pass), so re-read the live values.
        for e in enemies:
            e.adjust_hp_after_added([o for o in enemies if o is not e])

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
        """
        for enemy in list(self.enemies):
            if enemy.is_gone and not enemy.retained_after_death:
                continue
            if not enemy.performed_first_move:
                continue
            enemy.telegraph_next_move()

    def _execute_enemy_turn(self) -> None:
        self.current_side = "enemy"
        try:
            self._run_enemy_turns()
        finally:
            self.current_side = "player"

    def _run_enemy_turns(self) -> None:
        for enemy in list(self.enemies):
            # ExecuteEnemyTurn iterates every creature still IN the combat
            # (_state.ContainsCreature) and Creature.TakeTurn has no IsDead
            # guard, so a corpse the combat retained (a withered Decimillipede
            # segment) keeps taking turns — that is how it reaches REATTACH.
            if enemy.is_gone and not enemy.retained_after_death:
                continue

            # Clear block at the start of this enemy's turn. Two loops in C#
            # (CombatManager.cs:492-507): the clear, then AfterBlockCleared
            # UNCONDITIONALLY — the sim additionally gated the event on
            # `enemy.block > 0`, which the game does not.
            preventer: list = []
            if self.hooks.should_clear_block(enemy, preventer):
                enemy.block = 0
            else:
                self.hooks.after_preventing_block_clear(preventer, enemy)
            self.hooks.on_block_cleared(enemy)

            # Turn-start events (Poison, DemonForm, etc. can fire here).
            self.hooks.on_enemy_turn_start(enemy)
            if enemy.is_dead:
                if self._all_enemies_dead():
                    self._end_combat(player_won=True)
                    return
                if not enemy.retained_after_death:
                    continue
            if self.player.is_dead:
                self._end_combat(player_won=False)
                return

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
            if enemy.stunned:
                enemy.stunned = False
                move = getattr(enemy, "_current_move", None)
                if move is not None and move.id == STUN_STATE_ID:
                    enemy.take_turn(self._ctx())
            else:
                enemy.take_turn(self._ctx())
            # MonsterModel.PerformMove -> MoveStateMachine.OnMovePerformed:
            # from here on the monster's telegraphed move is no longer sticky,
            # so the player-turn-start pass rolls it.
            enemy.performed_first_move = True
            if self.player.is_dead:
                self.phase = Phase.COMBAT_OVER
                self.result = CombatResult(player_won=False, turns_taken=self.turn)
                return
            if self._all_enemies_dead():
                self._end_combat(player_won=True)
                return

            # Turn-end events (Regen, Ritual, per-enemy effects, etc.).
            self.hooks.on_enemy_turn_end(enemy)

        # Side-end: fires once after all enemies have acted (debuff ticks, etc.).
        if self.phase != Phase.COMBAT_OVER:
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
        if self.player.is_dead:
            self._end_combat(player_won=False)
        elif self._all_enemies_dead():
            self._end_combat(player_won=True)

    def _end_combat(self, player_won: bool) -> None:
        self.phase = Phase.COMBAT_OVER
        self.result = CombatResult(player_won=player_won, turns_taken=self.turn)
        self.hooks.on_combat_end(player_won)

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
            self.player.hand.remove(card)
            card.on_turn_end_in_hand(ctx)
            if self.player.is_dead:
                self._end_combat(player_won=False)
                return
            if card.is_ethereal and self.hooks.should_ethereal_trigger(card):
                self.player.exhaust_pile.append(card)
                # CardModel.cs:1692 — the other one.
                self.hooks.on_card_exhausted(card, caused_by_ethereal=True)
            else:
                self.player.discard_pile.append(card)
                self.hooks.on_card_discarded(card)

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
        self.hooks.on_energy_spent(card, actual_cost)
        self.player.hand.pop(hand_index)
        self._resolve_card_play(card, target_idx)

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)

        return True

    def auto_play(self, card: Card, target_idx: int | None = None) -> bool:
        """Play a card outside the normal hand-index / energy flow (mirrors
        CardCmd.AutoPlay): used by content that plays a card for free
        (Imbued enchantment turn 1, Whispering Earring). The card is removed
        from the hand if present; energy is NOT spent here (callers that must
        pay spend it themselves). Returns False if not in the player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return False
        if card in self.player.hand:
            self.player.hand.remove(card)
        self._resolve_card_play(card, target_idx, is_auto_play=True)
        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)
        return True

    def _resolve_card_play(self, card: Card, target_idx: int | None,
                           is_auto_play: bool = False) -> None:
        """Shared card-play resolution: result pile placement, play-count loop,
        exhaust-keyword move, and the played hook. The card must already be
        removed from the hand (or whichever pile it was played from)."""
        # Power cards are removed from the combat entirely when played;
        # everything else resolves from the discard pile. The game actually
        # holds the card in PileType.Play (a limbo pile) during OnPlay and only
        # moves it to its result pile (discard) AFTER the effect resolves
        # (CardCmd.cs:116). The sim keeps it in discard for simplicity, but
        # marks it as "being played" so a reshuffle its own effect triggers
        # excludes it (parity — see PlayerCombatState.reshuffle_discard_into_draw).
        if card.card_type != CardType.POWER:
            self.player.discard_pile.append(card)
            self.player._playing_card = card

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
        # BaseReplayCount (Hidden Gem) seeds the play count; enchantment
        # replays (Spiral/Glam) stack on top via the hook.
        play_count = self.hooks.modify_card_play_count(
            card, self.enemy, 1 + card.base_replay_count
        )
        # Attack plays are bracketed by the attack-command boundary (mirrors
        # AttackCommand firing BeforeAttack/AfterAttack) so "next attack"
        # powers on the player (Vigor from Akabeko) consume their stacks after
        # one full multi-hit attack.
        is_attack = card.card_type == CardType.ATTACK
        # ModifyCardPlayResultPileTypeAndPosition is consulted ONCE, when
        # `resultPileType` is computed for the CardPlay (CardModel.cs:1922) —
        # i.e. BEFORE the loop and before any CardPlayStarted entry for this
        # card exists. Nostalgia counts CardPlaysStarted this turn, so it must
        # not see the play it is deciding about. The MOVE still happens after
        # the loop, in the finally.
        result_pile = self.hooks.modify_card_play_result_pile(card, "discard")
        # CardModel.cs:1904-1965 builds a FRESH CardPlay each iteration
        # (PlayIndex = i, :1919-1928) and fires Hook.BeforeCardPlayed (:1929)
        # AND Hook.AfterCardPlayed (:1959) INSIDE the loop. The sim fired each
        # once per logical play, so a Throwing-Axe-doubled Strike advanced Pen
        # Nib's counter by 1 where the game advances it by 2 — from the first
        # combat of a run, the two engines doubled a different attack.
        for play_index in range(play_count):
            card.current_play_index = play_index
            self.hooks.before_card_played(card, played_target)
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
            # EnchantmentModel.OnPlay is a DIRECT in-loop call, not a hook
            # (CardModel.cs:1937-1945) — after the card's own OnPlay and before
            # Hook.AfterCardPlayed.
            if card.enchantment is not None:
                card.enchantment.on_play(card, played_target)
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
            if self._all_enemies_dead() or self.player.is_dead:
                break

        # OnPlay resolved: the card leaves limbo (moves to its result pile), so
        # later reshuffles include it normally again.
        self.player._playing_card = None

        # Exhaust keyword: move the played card from discard to exhaust.
        if card.exhausts and card in self.player.discard_pile:
            self.player.discard_pile.remove(card)
            self.player.exhaust_pile.append(card)
            self.hooks.on_card_exhausted(card)

        # Result-pile redirect (ModifyCardPlayResultPileTypeAndPosition):
        # Nostalgia sends the first Attack/Skill plays of the turn to the top
        # of the draw pile instead of the discard pile.
        if card in self.player.discard_pile and result_pile == "draw_top":
            self.player.discard_pile.remove(card)
            self.player.draw_pile.append(card)  # end of list = top of pile

    def auto_play_card(self, card: Card, target_idx: int | None = None) -> None:
        """Play a card for free (mirrors CardCmd.AutoPlay): no energy is spent.

        The card is removed from whichever pile currently holds it. Unplayable
        or hook-blocked cards move to the discard pile without being played;
        ANY_ENEMY cards target a random living enemy when target_idx is
        omitted. The played card ends in its normal result pile.
        """
        if self.phase == Phase.COMBAT_OVER or self.player.is_dead:
            return
        piles = (
            self.player.hand,
            self.player.draw_pile,
            self.player.discard_pile,
            self.player.exhaust_pile,  # e.g. Howl From Beyond replays itself
        )
        for pile in piles:
            if card in pile:
                pile.remove(card)
                break
        if not card.is_playable or not self.hooks.should_play_card(card, auto_play=True):
            # MoveToResultPileWithoutPlaying: no on_play, no played hook.
            self.player.discard_pile.append(card)
            return
        if card.target_type == TargetType.ANY_ENEMY and target_idx is None:
            living = [i for i, e in enumerate(self.enemies) if not e.is_gone]
            if not living:
                self.player.discard_pile.append(card)
                return
            # CardCmd.cs:77 — Rng.CombatTargets.NextItem(HittableEnemies).
            target_idx = self.combat_rng.targets.choice(living)
        if card.energy_cost_x:
            # AutoPlay captures X from current energy without spending it.
            card.captured_x = self.hooks.modify_x_value(card, self.player.energy)
        # BeforeCardPlayed fires for auto-plays too (0 energy spent) — powers
        # like Free Attack consume their stacks here.
        self.hooks.on_energy_spent(card, 0)
        self._resolve_card_play(card, target_idx, is_auto_play=True)

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)

    def select_cards(
        self,
        purpose: str,
        candidates: list[Card],
        count: int = 1,
        min_select: int | None = None,
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
        """
        # CardSelectCmd's first guard: every C# selection screen returns an
        # empty list once the combat is over or ending (CardSelectCmd.cs:194-199,
        # 277-285, 382-394, 694-707). The sim implemented only the
        # 0-candidate arm.
        if self.is_over_or_ending:
            return []
        if not candidates:
            return []
        count = min(count, len(candidates))
        floor = count if min_select is None else min(min_select, len(candidates))
        if count <= 0 and floor <= 0:
            return []
        if self.card_selector is not None:
            chosen = list(self.card_selector(purpose, list(candidates), count))[:count]
            return [c for c in chosen if c in candidates]
        if floor < count:
            # With a real minimum below the maximum the selectorless path must
            # be able to return fewer than `count` — including none at all.
            count = self._rng.randint(floor, count)
        if count <= 0:
            return []
        return self._rng.sample(candidates, count)

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
        potion.use(ctx, target)
        self.hooks.on_potion_used(potion, target)
        self._check_for_empty_hand()

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)
        return True

    def _check_for_empty_hand(self) -> None:
        """CombatManager.CheckForEmptyHand (CombatManager.cs:887-893).

        Two callers: CardModel.cs:1992 and PotionModel.cs:340 — so the game
        tests the hand after every card play AND every potion use, which is
        what makes Unceasing Top's draw reachable from all 51 potions. The
        end-of-turn flush (CombatManager.cs:880-883) explicitly EXCLUDES it.
        """
        if self.phase == Phase.COMBAT_OVER:
            return
        if not self.player.hand:
            self.hooks.on_hand_emptied(self.player)

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
        """Fire turn-end hooks, discard hand, run enemy turn, begin next player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return

        # PlayerTurnPhase.AutoPostPlay (CombatManager.cs:1160-1176): the
        # end-of-turn auto-plays drain in their own phase, entered STRICTLY
        # before Hook.BeforeTurnEnd.
        self.hooks.after_auto_post_play_phase_entered(self.player)
        if self.phase == Phase.COMBAT_OVER:
            return

        self.hooks.on_player_turn_end(self.player)
        if self.phase == Phase.COMBAT_OVER:
            # Turn-end effects can end the fight.
            return
        self._process_turn_end_cards()
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
        if self.hooks.should_take_extra_turn(self.player):
            self.hooks.on_extra_turn(self.player)
            self.turn += 1
            # No _roll_enemy_intents here: CombatManager.cs:478 gates the pass
            # on `!isExtraPlayerTurn`, so an extra player turn faces the same
            # intents (and takes no MonsterAi draw).
            self.player.start_turn()
            self._check_win_condition()
            return

        self._execute_enemy_turn()

        if self.phase != Phase.COMBAT_OVER:
            self.turn += 1
            # The enemy-intent pass runs inside StartTurn, before the player's
            # own turn setup draws anything (CombatManager.cs:478-484 precedes
            # SetupPlayerTurn at :510-523).
            self._roll_enemy_intents()
            self.player.start_turn()
            # CheckWinCondition right after the player's turn setup /
            # auto-pre-play phase (CombatManager.cs:573). A turn-start effect
            # can land the killing blow (Inferno's burst, a Poison tick) or kill
            # the player, and the game ends the fight there rather than handing
            # back a turn with no living enemies.
            if self.phase != Phase.COMBAT_OVER:
                if self._all_enemies_dead():
                    self._end_combat(player_won=True)
                elif self.player.is_dead:
                    self._end_combat(player_won=False)

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
        return (self.phase == Phase.COMBAT_OVER
                or self.player.is_dead
                or self._all_enemies_dead())
