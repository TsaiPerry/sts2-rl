from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .creatures import Creature
from .hooks import HookSystem

if TYPE_CHECKING:
    from .cards import Card
    from .potions import Potion


class PlayerCombatState(Creature):
    ENERGY_PER_TURN = 3
    DRAW_PER_TURN = 5
    MAX_HAND_SIZE = 10
    MAX_POTIONS = 3

    def __init__(
        self,
        max_hp: int,
        deck: list[Card],
        rng: random.Random,
        hooks: HookSystem,
        potions: list[Potion] | None = None,
    ) -> None:
        super().__init__(max_hp)
        self.side = "player"
        self.energy = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = deck.copy()
        self.discard_pile: list[Card] = []
        self.exhaust_pile: list[Card] = []
        self.potions: list[Potion] = list(potions or [])[: self.MAX_POTIONS]
        self._rng = rng
        self._hooks = hooks
        self._first_turn = True
        rng.shuffle(self.draw_pile)

    @property
    def all_cards(self) -> list[Card]:
        """Every card the player owns in this combat, across all piles
        (mirrors STS2's PlayerCombatState.AllCards)."""
        return self.hand + self.draw_pile + self.discard_pile + self.exhaust_pile

    def start_turn(self) -> None:
        """Reset block/energy, fire turn-start hooks, then draw."""
        # "This turn" card-cost modifiers (Stomp, Infernal Blade) expire.
        for card in self.all_cards:
            card.reset_turn_cost_modifiers()

        if self._hooks.should_clear_block(self):
            self.block = 0
            self._hooks.on_block_cleared(self)

        self.energy = self._hooks.modify_max_energy(self, self.ENERGY_PER_TURN)
        self._hooks.on_energy_reset(self)
        self._hooks.on_player_turn_start(self)

        draw_count = self._hooks.modify_hand_draw(self, self.DRAW_PER_TURN)
        if self._first_turn:
            self._first_turn = False
            # Innate cards move to the top of the draw pile and the first-turn
            # draw is raised to include all of them (mirrors CombatManager's
            # combat-start innate handling: MoveToTop + handDraw = max(...)).
            innates = [c for c in self.draw_pile if c.innate]
            if innates:
                for card in innates:
                    self.draw_pile.remove(card)
                self.draw_pile.extend(innates)  # end of list = top of pile
                draw_count = max(draw_count, len(innates))
        self._draw(draw_count, from_hand_draw=True)

    def discard_hand(self) -> None:
        """Discard all cards in hand to the discard pile, firing per-card hooks."""
        for card in list(self.hand):
            self._hooks.on_card_discarded(card)
        self.discard_pile.extend(self.hand)
        self.hand = []
        self._hooks.on_hand_emptied(self)

    def reshuffle_discard_into_draw(self) -> None:
        """Shuffle the discard pile into the empty draw pile (mirrors
        CardPileCmd.ShuffleIfNecessary's reshuffle step)."""
        self.draw_pile = self.discard_pile
        self.discard_pile = []
        self._rng.shuffle(self.draw_pile)
        self._hooks.on_shuffle(self)

    def _draw(self, n: int, from_hand_draw: bool = False) -> None:
        for _ in range(n):
            if len(self.hand) >= self.MAX_HAND_SIZE:
                break
            if not self._hooks.should_draw(self, from_hand_draw):
                break
            if not self.draw_pile:
                if not self.discard_pile:
                    break
                self.reshuffle_discard_into_draw()
            card = self.draw_pile.pop()
            self.hand.append(card)
            self._hooks.on_card_drawn(card, from_hand_draw)
