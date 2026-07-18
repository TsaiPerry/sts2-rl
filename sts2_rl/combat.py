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
from .player import PlayerCombatState
from .potions import Potion

if TYPE_CHECKING:
    from .relics import Relic
    from .rewards import RewardExtra


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
        encounter: Encounter | None = None,
        potions: list[Potion] | None = None,
        relics: list[Relic] | None = None,
        card_selector=None,
        max_hp: int | None = None,
        current_hp: int | None = None,
        room_type=None,
        max_potions: int | None = None,
        player_gold: int = 0,
    ) -> None:
        self._rng = rng or random.Random()
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
            starting_deck, self._rng, self.hooks, potions=potions,
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
            self.hooks, self._rng
        )
        # Relics are hook listeners for the whole combat (mirrors RelicModel :
        # AbstractModel with ShouldReceiveCombatHooks); attach() sets the
        # combat back-reference and registers them.
        self.relics: list[Relic] = list(relics or [])
        for relic in self.relics:
            relic.attach(self)
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
        # id(combat card) -> the run-deck card it was deep-copied from; the
        # sim's analogue of CardModel.DeckVersion. Populated by
        # RunState.create_combat; empty for room-less/standalone combats
        # (which have no deck, like a card with DeckVersion == null).
        self.deck_card_origins: dict[int, "Card"] = {}
        self.result: Optional[CombatResult] = None

        self.hooks.on_combat_start()
        self.player.start_turn()

    @property
    def enemy(self) -> Monster:
        """First living enemy; falls back to the first enemy if all are gone."""
        for e in self.enemies:
            if not e.is_gone:
                return e
        return self.enemies[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ctx(self) -> CombatCtx:
        return CombatCtx(self, self.player, self.enemies, self.hooks)

    def _all_enemies_dead(self) -> bool:
        # Minions (Kin Followers, Eye With Teeth) are secondary enemies: combat
        # is won once every primary enemy is dead or escaped, even if minions
        # survive.
        primaries = [e for e in self.enemies if "minion" not in e.powers]
        return all(e.is_gone for e in (primaries or self.enemies))

    def _execute_enemy_turn(self) -> None:
        self.current_side = "enemy"
        try:
            self._run_enemy_turns()
        finally:
            self.current_side = "player"

    def _run_enemy_turns(self) -> None:
        for enemy in list(self.enemies):
            if enemy.is_gone:
                continue

            # Clear block at the start of this enemy's turn.
            if enemy.block > 0 and self.hooks.should_clear_block(enemy):
                enemy.block = 0
                self.hooks.on_block_cleared(enemy)

            # Turn-start events (Poison, DemonForm, etc. can fire here).
            self.hooks.on_enemy_turn_start(enemy)
            if enemy.is_dead:
                if self._all_enemies_dead():
                    self._end_combat(player_won=True)
                    return
                continue
            if self.player.is_dead:
                self._end_combat(player_won=False)
                return

            # Execute the enemy's move, or skip it if stunned (turn-start and
            # turn-end effects like Poison still fire on a stunned turn).
            if enemy.stunned:
                enemy.stunned = False
            else:
                enemy.take_turn(self._ctx())
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
                self.hooks.on_card_exhausted(card)

        # Cards with a turn-end effect: fire the effect, then exhaust or discard.
        for card in [c for c in self.player.hand if c.has_turn_end_in_hand_effect]:
            self.player.hand.remove(card)
            card.on_turn_end_in_hand(ctx)
            if self.player.is_dead:
                self._end_combat(player_won=False)
                return
            if card.is_ethereal and self.hooks.should_ethereal_trigger(card):
                self.player.exhaust_pile.append(card)
                self.hooks.on_card_exhausted(card)
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
        self._resolve_card_play(card, target_idx)
        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)
        return True

    def _resolve_card_play(self, card: Card, target_idx: int | None) -> None:
        """Shared card-play resolution: result pile placement, play-count loop,
        exhaust-keyword move, and the played hook. The card must already be
        removed from the hand (or whichever pile it was played from)."""
        # Power cards are removed from the combat entirely when played;
        # everything else resolves from the discard pile.
        if card.card_type != CardType.POWER:
            self.player.discard_pile.append(card)

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
        self.hooks.before_card_played(card, played_target)
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
        for _ in range(play_count):
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
            if self._all_enemies_dead() or self.player.is_dead:
                break

        # Exhaust keyword: move the played card from discard to exhaust.
        if card.exhausts and card in self.player.discard_pile:
            self.player.discard_pile.remove(card)
            self.player.exhaust_pile.append(card)
            self.hooks.on_card_exhausted(card)

        # Result-pile redirect (ModifyCardPlayResultPileTypeAndPosition):
        # Nostalgia sends the first Attack/Skill plays of the turn to the top
        # of the draw pile instead of the discard pile.
        if card in self.player.discard_pile:
            if self.hooks.modify_card_play_result_pile(card, "discard") == "draw_top":
                self.player.discard_pile.remove(card)
                self.player.draw_pile.append(card)  # end of list = top of pile

        self.hooks.on_card_played(card)

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
            target_idx = self._rng.choice(living)
        if card.energy_cost_x:
            # AutoPlay captures X from current energy without spending it.
            card.captured_x = self.hooks.modify_x_value(card, self.player.energy)
        # BeforeCardPlayed fires for auto-plays too (0 energy spent) — powers
        # like Free Attack consume their stacks here.
        self.hooks.on_energy_spent(card, 0)
        self._resolve_card_play(card, target_idx)

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)

    def select_cards(
        self,
        purpose: str,
        candidates: list[Card],
        count: int = 1,
    ) -> list[Card]:
        """In-combat card selection (mirrors CardSelectCmd's selection screens).

        purpose is a short label describing the choice ("upgrade", "exhaust",
        "from_discard", ...) so a policy can distinguish selection contexts.
        The choice is delegated to self.card_selector — a callable
        (purpose, candidates, count) -> list[Card] — when one is installed
        (by tests, the env, or an agent); otherwise up to count cards are
        picked uniformly at random with the combat RNG.
        """
        if count <= 0 or not candidates:
            return []
        count = min(count, len(candidates))
        if self.card_selector is not None:
            chosen = list(self.card_selector(purpose, list(candidates), count))[:count]
            return [c for c in chosen if c in candidates]
        return self._rng.sample(candidates, count)

    def use_potion(self, slot: int, target_idx: int | None = None) -> bool:
        """Use the potion in the given slot (removed on use).

        For targeted potions, target_idx selects the enemy (defaults to the
        first living enemy). Returns False if the action is invalid.
        """
        if self.phase != Phase.PLAYER_TURN:
            return False
        if slot < 0 or slot >= len(self.player.potions):
            return False

        potion = self.player.potions.pop(slot)
        ctx = self._ctx()
        target = ctx.resolve_target(target_idx) if potion.targeted else None
        potion.use(ctx, target)
        self.hooks.on_potion_used(potion, target)

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)
        return True

    def end_turn(self) -> None:
        """Fire turn-end hooks, discard hand, run enemy turn, begin next player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return

        # Hook.ShouldTakeExtraTurn (Pael's Eye): a listener may claim an extra
        # player turn — the enemy side is skipped entirely and a fresh player
        # turn starts (block clear → energy → hooks → draw). on_extra_turn
        # lets the granter do its bookkeeping (exhaust the hand, mark used).
        if self.hooks.should_take_extra_turn(self.player):
            self.hooks.on_extra_turn(self.player)
            self.turn += 1
            self.player.start_turn()
            return

        self.hooks.on_player_turn_end(self.player)
        if self.phase == Phase.COMBAT_OVER:
            # Turn-end effects (e.g. Stampede auto-plays) can end the fight.
            return
        self._process_turn_end_cards()
        if self.phase == Phase.COMBAT_OVER:
            return
        if self.hooks.should_flush_hand():
            self.player.discard_hand()
        self._execute_enemy_turn()

        if self.phase != Phase.COMBAT_OVER:
            self.turn += 1
            self.player.start_turn()
            if self.player.is_dead and self.phase != Phase.COMBAT_OVER:
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
