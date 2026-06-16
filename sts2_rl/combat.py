from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .cards import Card, STRIKE, DEFEND
from .cmds import DamageCmd, StrengthCmd
from .hooks import HookSystem
from .monsters import FuzzyWurmCrawler, MoveType
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
    enemy: FuzzyWurmCrawler
    hooks: HookSystem


class CombatState:
    PLAYER_MAX_HP = 80

    def __init__(
        self,
        starting_deck: list[Card] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._rng = rng or random.Random()

        if starting_deck is None:
            starting_deck = [STRIKE] * 5 + [DEFEND] * 4

        self.hooks = HookSystem()
        self.player = PlayerCombatState(
            self.PLAYER_MAX_HP, starting_deck, self._rng, self.hooks
        )
        self.enemy = FuzzyWurmCrawler(rng=self._rng)
        self.phase = Phase.PLAYER_TURN
        self.turn = 1
        self.result: Optional[CombatResult] = None

        self.hooks.on_combat_start()
        self.player.start_turn()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ctx(self) -> CombatCtx:
        return CombatCtx(self, self.player, self.enemy, self.hooks)

    def _execute_enemy_turn(self) -> None:
        if self.enemy.block > 0 and self.hooks.should_clear_block(self.enemy):
            self.enemy.block = 0
            self.hooks.on_block_cleared(self.enemy)

        self.hooks.on_enemy_turn_start(self.enemy)
        move = self.enemy.current_move

        if move.move_type == MoveType.ATTACK:
            DamageCmd.deal(
                self.hooks,
                self.player,
                move.damage + self.enemy.strength,
                dealer=self.enemy,
            )
            if self.player.is_dead:
                self.phase = Phase.COMBAT_OVER
                self.result = CombatResult(player_won=False, turns_taken=self.turn)
        elif move.move_type == MoveType.BUFF:
            StrengthCmd.apply(self.hooks, self.enemy, move.strength_gain)

        self.enemy.advance_move()
        self.hooks.on_enemy_turn_end(self.enemy)

    def _end_combat(self, player_won: bool) -> None:
        self.phase = Phase.COMBAT_OVER
        self.result = CombatResult(player_won=player_won, turns_taken=self.turn)
        self.hooks.on_combat_end(player_won)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_card(self, hand_index: int) -> bool:
        """Play the card at hand_index. Returns False if the action is invalid."""
        if self.phase != Phase.PLAYER_TURN:
            return False
        if hand_index < 0 or hand_index >= len(self.player.hand):
            return False

        card = self.player.hand[hand_index]
        actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
        if actual_cost > self.player.energy:
            return False

        self.player.energy -= actual_cost
        self.hooks.on_energy_spent(card, actual_cost)
        self.player.hand.pop(hand_index)
        self.player.discard_pile.append(card)

        play_count = self.hooks.modify_card_play_count(card, self.enemy, 1)
        for _ in range(play_count):
            card.on_play(self._ctx())

        self.hooks.on_card_played(card)

        if self.enemy.is_dead:
            self._end_combat(player_won=True)

        return True

    def end_turn(self) -> None:
        """Fire turn-end hooks, discard hand, run enemy turn, begin next player turn."""
        if self.phase != Phase.PLAYER_TURN:
            return

        self.hooks.on_player_turn_end(self.player)
        self.player.discard_hand()
        self._execute_enemy_turn()

        if self.phase != Phase.COMBAT_OVER:
            self.turn += 1
            self.player.start_turn()

    def valid_actions(self) -> list[int]:
        """0 = end turn, 1+ = play card at hand index (action - 1)."""
        if self.phase != Phase.PLAYER_TURN:
            return []
        actions = [0]
        for i, card in enumerate(self.player.hand):
            actual_cost = self.hooks.modify_card_energy_cost(card, card.energy_cost)
            if actual_cost <= self.player.energy:
                actions.append(i + 1)
        return actions

    @property
    def is_over(self) -> bool:
        return self.phase == Phase.COMBAT_OVER
