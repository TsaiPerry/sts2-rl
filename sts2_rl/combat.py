from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .cards import Card, make_card, TargetType
from .cmds import DamageCmd
from .hooks import HookSystem
from .monsters import Encounter, Monster, FUZZY_WURM_ENCOUNTER
from .player import PlayerCombatState


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
        """First living enemy; falls back to the first enemy if all are dead."""
        for e in self.enemies:
            if not e.is_dead:
                return e
        return self.enemies[0]

    def resolve_target(self, target_idx: int | None) -> Monster:
        """Return the indexed enemy if it is alive; otherwise the first living enemy."""
        if target_idx is not None and target_idx < len(self.enemies) and not self.enemies[target_idx].is_dead:
            return self.enemies[target_idx]
        return self.enemy


class CombatState:
    PLAYER_MAX_HP = 80

    def __init__(
        self,
        starting_deck: list[Card] | None = None,
        rng: random.Random | None = None,
        encounter: Encounter | None = None,
    ) -> None:
        self._rng = rng or random.Random()

        if starting_deck is None:
            starting_deck = [make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)]

        self.hooks = HookSystem()
        self.player = PlayerCombatState(
            self.PLAYER_MAX_HP, starting_deck, self._rng, self.hooks
        )
        self.enemies: list[Monster] = (encounter or FUZZY_WURM_ENCOUNTER).create_monsters(
            self.hooks, self._rng
        )
        self.phase = Phase.PLAYER_TURN
        self.turn = 1
        self.result: Optional[CombatResult] = None

        self.hooks.on_combat_start()
        self.player.start_turn()

    @property
    def enemy(self) -> Monster:
        """First living enemy; falls back to the first enemy if all are dead."""
        for e in self.enemies:
            if not e.is_dead:
                return e
        return self.enemies[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ctx(self) -> CombatCtx:
        return CombatCtx(self, self.player, self.enemies, self.hooks)

    def _all_enemies_dead(self) -> bool:
        return all(e.is_dead for e in self.enemies)

    def _execute_enemy_turn(self) -> None:
        for enemy in list(self.enemies):
            if enemy.is_dead:
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

            # Execute the enemy's move (attack / buff / etc.).
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
        actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
        if actual_cost > self.player.energy:
            return False

        self.player.energy -= actual_cost
        self.hooks.on_energy_spent(card, actual_cost)
        self.player.hand.pop(hand_index)
        self.player.discard_pile.append(card)

        play_count = self.hooks.modify_card_play_count(card, self.enemy, 1)
        for _ in range(play_count):
            if card.target_type == TargetType.ALL_ENEMIES and not card.handles_own_routing:
                # Framework routes: call on_play once per living enemy.
                for idx, e in enumerate(self.enemies):
                    if e.is_dead:
                        continue
                    card.on_play(self._ctx(), idx)
                    if self._all_enemies_dead() or self.player.is_dead:
                        break
            else:
                # Card handles its own routing (or doesn't need enemy iteration).
                card.on_play(self._ctx(), target_idx)
            if self._all_enemies_dead():
                self._end_combat(player_won=True)
                return True
            if self.player.is_dead:
                self._end_combat(player_won=False)
                return True

        self.hooks.on_card_played(card)

        if self._all_enemies_dead() and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=True)
        elif self.player.is_dead and self.phase != Phase.COMBAT_OVER:
            self._end_combat(player_won=False)

        return True

    def end_turn(self) -> None:
        """Fire turn-end hooks, discard hand, run enemy turn, begin next player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return

        self.hooks.on_player_turn_end(self.player)
        self._process_turn_end_cards()
        if self.phase == Phase.COMBAT_OVER:
            return
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
            actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
            if actual_cost <= self.player.energy:
                actions.append(i + 1)
        return actions

    @property
    def is_over(self) -> bool:
        return self.phase == Phase.COMBAT_OVER
