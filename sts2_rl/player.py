"""PlayerCombatState — the player side of a combat, mirroring STS2's
PlayerCombatState.

Extends Creature with energy, the four card piles (hand / draw / discard /
exhaust), and potions. Owns the card-flow verbs: `start_turn` (clear block →
reset energy → turn-start hooks → draw, with innate-card handling on turn 1),
`discard_hand` (respecting Retain), `reshuffle_discard_into_draw`, and the
low-level `_draw`. Constants (ENERGY_PER_TURN, DRAW_PER_TURN, MAX_HAND_SIZE,
MAX_POTIONS) live here as class attributes.
"""
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
        max_potions: int | None = None,
    ) -> None:
        super().__init__(max_hp)
        self.side = "player"
        self.energy = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = deck.copy()
        self.discard_pile: list[Card] = []
        self.exhaust_pile: list[Card] = []
        # Belt size defaults to the base 3; runs pass their own (Phial
        # Holster grows RunState.max_potions).
        self.max_potions = max_potions if max_potions is not None else self.MAX_POTIONS
        self.potions: list[Potion] = list(potions or [])[: self.max_potions]
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

        # Energy reset — or add-to-current when a listener vetoes the reset
        # (mirrors ShouldPlayerResetEnergy → ResetEnergy / AddMaxEnergyToCurrent).
        gained = self._hooks.modify_max_energy(self, self.ENERGY_PER_TURN)
        if self._hooks.should_reset_energy(self):
            self.energy = gained
        else:
            self.energy += gained
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
        # Post-draw turn-start slot (the game's AfterPlayerTurnStart /
        # player-side AfterSideTurnStart, both of which run after the draw).
        self._hooks.on_player_turn_started(self)

    def discard_hand(self) -> None:
        """Discard the hand to the discard pile at end of turn, firing per-card
        hooks. Retain cards stay in hand (mirrors the end-of-turn flush in
        CombatManager skipping ShouldRetainThisTurn cards)."""
        flushed = [c for c in self.hand if not c.retain]
        for card in flushed:
            self._hooks.on_card_discarded(card)
        self.discard_pile.extend(flushed)
        self.hand = [c for c in self.hand if c.retain]
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
