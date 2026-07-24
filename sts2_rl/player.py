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

from typing import TYPE_CHECKING

from .creatures import Creature
from .hooks import HookSystem

if TYPE_CHECKING:
    from .cards import Card
    from .potions import Potion


def _compare_to_key(card: "Card") -> "tuple[str, int]":
    """CardModel.CompareTo's sort key (CardModel.cs:2242): the ModelId first —
    `string.Compare(Entry, other.Entry, StringComparison.Ordinal)`
    (ModelId.cs:49) over the game's UPPERCASE entry — then CurrentUpgradeLevel.

    Case matters: an ordinal compare puts `_` (0x5F) *after* the uppercase
    letters but *before* the lowercase ones, so sorting the sim's lowercase
    slugs orders `blood_wall`/`bloodletting` and
    `jack_of_all_trades`/`jackpot` the opposite way round from the game.
    Cards that compare equal keep their incoming order (Python's sort is
    stable), so the caller must pass the pile in the GAME's orientation."""
    return (card.id.upper(), card.upgrade_level)


def stable_shuffled_cards(cards: "list[Card]", combat_rng) -> "list[Card]":
    """`cards.ToList().StableShuffle(Rng.Shuffle)` — a shuffled COPY, in the
    game's own orientation (index 0 is the game's `First()`).

    Content that picks a card at random by shuffling a pile and taking the
    front (Catastrophe) must burn the shuffle's N-1 draws, not one. The
    stabilizing sort is the same CardModel.CompareTo key `_shuffle_draw_pile`
    uses, and is parity-only for the same reason: legacy stays byte-for-byte.
    """
    out = list(cards)
    if combat_rng.is_parity:
        out.sort(key=_compare_to_key)
    combat_rng.shuffle.shuffle(out)
    return out


class PlayerCombatState(Creature):
    ENERGY_PER_TURN = 3
    DRAW_PER_TURN = 5
    MAX_HAND_SIZE = 10
    MAX_POTIONS = 3

    def __init__(
        self,
        max_hp: int,
        deck: list[Card],
        combat_rng,
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
        self._combat_rng = combat_rng
        self._hooks = hooks
        self._first_turn = True
        # The card currently mid-OnPlay, if any. The game holds a card being
        # played in PileType.Play (limbo), not the discard, so a reshuffle its
        # own effect triggers must not shuffle it back into the draw pile
        # (CardCmd.cs:116; see reshuffle_discard_into_draw). Set by
        # Combat._resolve_card_play for the duration of the play.
        self._playing_card: Card | None = None
        # Combat-start draw-pile randomization is CardPile.RandomizeOrderInternal
        # -> UnstableShuffle (Fisher-Yates, NO stabilizing sort), unlike the
        # mid-combat reshuffle which is a StableShuffle. Hence stable=False here.
        self._shuffle_draw_pile(stable=False)

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
        held = self._playing_card
        if self._combat_rng.is_parity and held is not None and held in self.discard_pile:
            # A card mid-OnPlay lives in PileType.Play (limbo), not the discard,
            # so a reshuffle its own effect triggers (e.g. Pommel Strike drawing
            # the draw pile empty) must NOT shuffle it into the draw pile — the
            # game reshuffles discard+draw WITHOUT the being-played card, then
            # the card lands in the (now-empty) discard as its result pile after
            # OnPlay. Hold it back so the shuffled set matches the game exactly.
            # Legacy keeps the old byte-for-byte behavior (whole discard).
            self.draw_pile = [c for c in self.discard_pile if c is not held]
            self.discard_pile = [held]
        else:
            self.draw_pile = self.discard_pile
            self.discard_pile = []
        # A mid-combat reshuffle is CardPileCmd.Shuffle -> StableShuffle.
        self._shuffle_draw_pile(stable=True)
        self._hooks.on_shuffle(self)

    def shuffle_draw_and_discard(self) -> None:
        """CardPileCmd.Shuffle: shuffle the discard pile AND the whole current
        draw pile into a new draw pile (Bottled Potential).

        `reshuffle_discard_into_draw` is the ShuffleIfNecessary path, which only
        ever runs with an empty draw pile; the explicit command shuffles both
        piles together (`list = discard.ToList(); list.AddRange(drawPileCards);
        list.StableShuffle(Rng.Shuffle)`), so the draw pile's contents survive
        into the new order. Same PileType.Play limbo rule as the reshuffle: a
        card mid-OnPlay is in neither pile."""
        held = self._playing_card
        discard = self.discard_pile
        if self._combat_rng.is_parity and held is not None and held in discard:
            discard = [c for c in discard if c is not held]
            self.discard_pile = [held]
        else:
            self.discard_pile = []
        self.draw_pile = discard + self.draw_pile
        self._shuffle_draw_pile(stable=True)
        self._hooks.on_shuffle(self)

    def _shuffle_draw_pile(self, stable: bool) -> None:
        """Shuffle the draw pile via the Shuffle stream.

        The game has two draw-pile shuffles that both draw from the same
        Shuffle stream but differ in one step:

          - combat start: CardPile.RandomizeOrderInternal -> UnstableShuffle
            (Fisher-Yates only), `stable=False`.
          - reshuffle:    CardPileCmd.Shuffle -> StableShuffle, `stable=True`,
            which SORTS the pile into a canonical order first so the result is
            INDEPENDENT of the pile's incoming (play) order, THEN Fisher-Yates.

        In parity mode we reproduce both. The stabilizing sort mirrors the
        game's CardModel.CompareTo: first ModelId ordinal (Category.Entry) — the
        sim card `id` is a lowercase slug whose ordinal order matches the game
        Entry ordinal for the cards seen so far (bash < defend < strike, etc.)
        — then, for cards of the same id, CurrentUpgradeLevel (CardModel.cs
        CompareTo). The upgrade tiebreak matters whenever a pile holds both a
        base and an upgraded copy of one card (e.g. Defend + Defend+): the game
        sorts the upgraded copy AFTER the base regardless of their incoming
        discard order, so which variant lands on top after the Fisher-Yates is
        decided by upgrade level, not by play order. (A game-id override map can
        be added later if a card whose slug diverges from its game Entry order
        turns up.) Finally, the game stores the pile top-at-index-0 but the sim
        draws off the END of the list (its top), so reverse to reproduce the
        game's front-to-back draw order under the sim's top=end convention.

        Legacy is byte-for-byte unchanged: the shared random.Random shuffles in
        place with no sort and no reorientation."""
        if stable and self._combat_rng.is_parity:
            self.draw_pile.sort(key=_compare_to_key)
        self._combat_rng.shuffle.shuffle(self.draw_pile)
        if self._combat_rng.is_parity:
            self.draw_pile.reverse()

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
                # AfterShuffle hooks (e.g. Stratagem) can drain the pile;
                # the game re-checks after ShuffleIfNecessary and stops.
                if not self.draw_pile:
                    break
            card = self.draw_pile.pop()  # end of list = top of pile
            self.hand.append(card)
            self._hooks.on_card_drawn(card, from_hand_draw)
