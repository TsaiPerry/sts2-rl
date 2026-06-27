from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .creatures import Creature
from .hooks import HookSystem

if TYPE_CHECKING:
    from .cards import Card


class PlayerCombatState(Creature):
    ENERGY_PER_TURN = 3
    DRAW_PER_TURN = 5
    MAX_HAND_SIZE = 10

    def __init__(
        self,
        max_hp: int,
        deck: list[Card],
        rng: random.Random,
        hooks: HookSystem,
    ) -> None:
        super().__init__(max_hp)
        self.side = "player"
        self.energy = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = deck.copy()
        self.discard_pile: list[Card] = []
        self.exhaust_pile: list[Card] = []
        self._rng = rng
        self._hooks = hooks
        rng.shuffle(self.draw_pile)

    def start_turn(self) -> None:
        """Reset block/energy, fire turn-start hooks, then draw."""
        if self._hooks.should_clear_block(self):
            self.block = 0
            self._hooks.on_block_cleared(self)

        self.energy = self._hooks.modify_max_energy(self, self.ENERGY_PER_TURN)
        self._hooks.on_energy_reset(self)
        self._hooks.on_player_turn_start(self)

        draw_count = self._hooks.modify_hand_draw(self, self.DRAW_PER_TURN)
        self._draw(draw_count)

    def discard_hand(self) -> None:
        """Discard all cards in hand to the discard pile, firing per-card hooks."""
        for card in list(self.hand):
            self._hooks.on_card_discarded(card)
        self.discard_pile.extend(self.hand)
        self.hand = []
        self._hooks.on_hand_emptied(self)

    def _draw(self, n: int) -> None:
        for _ in range(n):
            if len(self.hand) >= self.MAX_HAND_SIZE:
                break
            if not self._hooks.should_draw(self):
                break
            if not self.draw_pile:
                if not self.discard_pile:
                    break
                self.draw_pile = self.discard_pile
                self.discard_pile = []
                self._rng.shuffle(self.draw_pile)
                self._hooks.on_shuffle(self)
            card = self.draw_pile.pop()
            self.hand.append(card)
            self._hooks.on_card_drawn(card)
