"""Port of NetCombatCardDb (src/Core/GameActions/Multiplayer/NetCombatCardDb.cs).

Assigns each combat card a contiguous per-combat uint id by identity, walking
piles in the game's fixed AllPiles order (Hand, DrawPile, DiscardPile,
ExhaustPile, PlayPile) at StartCombat, then id'ing newly-added cards in add
order. Consumes no RNG; it is the oracle the harness drives PlayCard by.

Timing parity (the subtle part): the game ids cards in `StartCombat`, which
runs right AFTER `PopulateCombatState` shuffles the deck into the draw pile but
BEFORE the opening hand is drawn (`CombatManager.StartCombatInternal`:
PopulateCombatState -> NetCombatCardDb.StartCombat ... StartTurn's draw runs
much later). So the game ids the full shuffled draw pile top-to-bottom, and the
opening hand — drawn from that same top — inherits ids 0..handSize-1 in draw
order. The sim, by contrast, draws the opening hand during combat construction
(before this db is even created) and stores its draw pile top-at-END (the
parity shuffle reverses it). To reproduce the game's StartCombat order from the
post-draw sim state we walk `hand + reversed(draw_pile)`: the opening hand is
the pile's top cards in draw order, and the remaining draw pile reversed is the
rest of the shuffled pile front-to-back. (No innate cards in the ported starter
pools, so the game's pre-MoveToTop id order and the sim's post-MoveToTop draw
coincide; revisit if an innate card enters scope.)
"""
from __future__ import annotations


class CombatCardDb:
    def __init__(self) -> None:
        self._next = 0
        self._id_to_card: dict[int, object] = {}
        self._card_to_id: dict[int, int] = {}   # keyed by id(card)

    def ordered_piles(self, combat) -> list[list]:
        p = combat.player
        # `PlayerCombatState.AllPiles` (PlayerCombatState.cs:70-80): Hand,
        # Draw, Discard, Exhaust, PLAY — five piles, Play last. The fifth one
        # is what keeps a card mid-OnPlay resolvable in this db (round 13 R5;
        # before it, a resolving card was parked in the discard pile and the
        # walk found it there by accident).
        return [p.hand, p.draw_pile, p.discard_pile, p.exhaust_pile, p.play_pile]

    def start_order(self, combat) -> list:
        """The cards in the game's StartCombat id order, reconstructed from the
        post-opening-draw sim state (see the module docstring): the opening
        hand (draw order) followed by the remaining draw pile reversed (the
        sim draws off the pile's END, so its front-to-back game order is the
        reverse of the stored list).

        Timing parity for turn-1 card generation: the game ids the shuffled deck
        at StartCombat, which is BEFORE the opening turn's post-draw effects run
        (AfterPlayerTurnStart — Vexing Puzzlebox, etc.). The sim, however, fires
        `start_turn()` during combat construction, so a generated card is already
        in hand by the time this db starts. Exclude those non-deck cards here so
        they inherit their id from `refresh` (add order) AFTER the deck's 0..N-1,
        exactly as the game assigns them. Deck cards are the ones with a
        `deck_card_origins` entry (their CardModel.DeckVersion); standalone
        combats have no origins map and no generation, so nothing is filtered."""
        p = combat.player
        origins = combat.deck_card_origins
        ordered = list(p.hand) + list(reversed(p.draw_pile))
        if origins:
            ordered = [c for c in ordered if id(c) in origins]
        return ordered

    def _id_if_necessary(self, card) -> None:
        if id(card) not in self._card_to_id:
            self._card_to_id[id(card)] = self._next
            self._id_to_card[self._next] = card
            self._next += 1

    def start(self, combat) -> None:
        self._next = 0
        self._id_to_card.clear()
        self._card_to_id.clear()
        for card in self.start_order(combat):
            self._id_if_necessary(card)
        # Defensive: id any card that a combat-start effect placed outside the
        # hand/draw piles (discard/exhaust) in AllPiles order.
        self.refresh(combat)

    def refresh(self, combat) -> None:
        for pile in self.ordered_piles(combat):
            for card in pile:
                self._id_if_necessary(card)

    def get(self, card_id: int):
        return self._id_to_card[card_id]

    def id_of(self, card) -> int:
        return self._card_to_id[id(card)]
