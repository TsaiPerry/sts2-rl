"""Port of NetCombatCardDb (src/Core/GameActions/Multiplayer/NetCombatCardDb.cs).

Assigns each combat card a contiguous per-combat uint id by identity. It is the
oracle the replay harness resolves a recorded `PlayCard <id>` through, and it
consumes no RNG.

**Ids are assigned WHEN A CARD IS ADDED; nothing is ever reconstructed after
the fact.** C# subscribes to each of the five combat piles'
`CardPile.ContentsChanged` at StartCombat (NetCombatCardDb.cs:48-58) and
`CardPile.AddInternal` raises that event once per non-silent add
(CardPile.cs:102-106), so `OnPileContentsChanged` (:105-111) walks the pile and
`IdCardIfNecessary` (:113-127) stamps the one card that is new. The id order is
therefore simply:

  1. the shuffled draw pile as it stands at `StartCombat`, then
  2. every later card in the order it ENTERED a pile.

Timing parity, and the reason this file is a port rather than a walk:
`NetCombatCardDb.StartCombat` is called from `CombatManager.SetUpCombat`
(CombatManager.cs:372) immediately after every player's `PopulateCombatState`
(:370) has cloned the deck into the draw pile and `RandomizeOrderInternal`d it,
and BEFORE the `AddCreature` loop, before `Hook.BeforeCombatStart` and long
before `StartTurn` draws the opening hand (CombatManager.cs:418). So the game
ids the full shuffled draw pile top-to-bottom while the hand is still empty,
and everything turn 1 generates — a relic's `BeforeHandDraw` cards, then the
opening draw, then an `AfterPlayerTurnStart` card — is stamped afterwards in
add order.

The sim's equivalent instant is inside `CombatState.__init__`, right after
`PlayerCombatState.__init__` has shuffled the deck into the draw pile and
before anything can react (`CombatState` starts the db there when it is
constructed with `track_card_ids=True`); later cards are stamped by
`CardPileCmd._enter_combat`, the sim's one "a new card entered a combat pile"
step.

This used to RECONSTRUCT the order post-draw instead, by walking
hand-then-draw and filtering to deck cards, and that was a harness bug with
real consequences: with Blessed Antler shuffling 3 Dazed into the draw pile at
`BeforeHandDraw` and Vexing Puzzlebox adding a card at `AfterPlayerTurnStart`,
the game ids the three Dazed 23-25 (all still in the draw pile) and the
Puzzlebox card 26, while the reconstruction gave the one Dazed that happened to
be drawn an early id and slid the Puzzlebox card in front of its siblings — so
a recorded `PlayCard 26` resolved to a Dazed and the fight force-won.

Pile ORIENTATION is the one place the two engines disagree structurally: a C#
`CardPile` is top-first (`MoveToTopInternal` is `Insert(0, ...)`,
`CardPileCmd.cs:843` draws `FirstOrDefault()`), while the sim's `draw_pile`
stores its top at the END. `AllPiles.SelectMany(p => p.Cards)` therefore
corresponds to `hand + reversed(draw_pile) + discard + exhaust + play` here —
see `ordered_piles`, which is the only place in the sim that flips the draw
pile for an ORDER-sensitive read (`PlayerCombatState.all_cards` deliberately
does not, because none of its consumers are).
"""
from __future__ import annotations


class CombatCardDb:
    def __init__(self, combat=None) -> None:
        self._next = 0
        self._id_to_card: dict[int, object] = {}
        self._card_to_id: dict[int, int] = {}   # keyed by id(card)
        if combat is not None:
            self.start_combat(combat)

    def ordered_piles(self, combat) -> list[list]:
        """`PlayerCombatState.AllPiles` (PlayerCombatState.cs:70-80) in its
        declared order — Hand, Draw, Discard, Exhaust, PLAY — each pile
        top-first, which for the sim's bottom-first `draw_pile` means reversed.

        The fifth (Play) leg is what keeps a card mid-`OnPlay` resolvable here
        (round 13 R5; before it, a resolving card was parked in the discard
        pile and the walk found it there by accident).
        """
        p = combat.player
        return [p.hand, list(reversed(p.draw_pile)), p.discard_pile,
                p.exhaust_pile, p.play_pile]

    def _id_if_necessary(self, card) -> None:
        """`IdCardIfNecessary` (NetCombatCardDb.cs:113-127)."""
        if id(card) not in self._card_to_id:
            self._card_to_id[id(card)] = self._next
            self._id_to_card[self._next] = card
            self._next += 1

    def start_combat(self, combat) -> None:
        """`StartCombat` (NetCombatCardDb.cs:33-61): clear, then id every card
        in `AllPiles` order. Called at the game's own instant — see the module
        docstring — when only the shuffled draw pile is populated."""
        self._next = 0
        self._id_to_card.clear()
        self._card_to_id.clear()
        self.refresh(combat)

    def on_card_added(self, card) -> None:
        """The `ContentsChanged` subscription for ONE non-silent
        `CardPile.AddInternal` (CardPile.cs:102-106 -> NetCombatCardDb.cs:105).

        `OnPileContentsChanged` re-walks the whole pile, but every other card
        in it already carries an id, so the add-order stamp below is exactly
        equivalent — and unlike a walk it does not depend on where in the pile
        the card landed (`add_to_draw` inserts at a random index).
        """
        self._id_if_necessary(card)

    def refresh(self, combat) -> None:
        """`OnPileContentsChanged` as a BACKSTOP, over all five piles.

        Every card that enters a pile through `CardPileCmd` is stamped at add
        time by `on_card_added`, so this is normally a no-op. It exists for the
        handful of sim sites that still mutate a pile list directly instead of
        going through a pile command (`cards/primal_force.py` swaps Attacks in
        the hand for Giant Rocks in place) — those cards would otherwise never
        be id'd at all. Walking `AllPiles` order is what C# would give them,
        since a direct `_cards` mutation is likewise only picked up by the next
        `ContentsChanged` on that pile.
        """
        for pile in self.ordered_piles(combat):
            for card in pile:
                self._id_if_necessary(card)

    def get(self, card_id: int):
        return self._id_to_card[card_id]

    def id_of(self, card) -> int:
        return self._card_to_id[id(card)]
