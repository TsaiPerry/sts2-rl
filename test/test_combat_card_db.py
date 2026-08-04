# test/test_combat_card_db.py
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.combat_card_db import CombatCardDb


def test_ids_are_contiguous_over_allpiles_order():
    c = CombatState(rng=random.Random(0), track_card_ids=True)
    db = c.card_db
    every = (c.player.hand + c.player.draw_pile
             + c.player.discard_pile + c.player.exhaust_pile)
    ids = sorted(db.id_of(card) for card in every)
    assert ids == list(range(len(every)))          # 0..N-1, no gaps
    # round-trips
    for card in every:
        assert db.get(db.id_of(card)) is card


def test_the_shuffled_draw_pile_is_id_d_top_first_before_the_opening_draw():
    """`NetCombatCardDb.StartCombat` runs at CombatManager.cs:372 — after
    `PopulateCombatState` shuffled the deck into the draw pile and BEFORE
    `StartTurn` draws the opening hand — and walks each `CardPile` top-first.

    So id 0 is the top of the shuffled pile, i.e. the FIRST card drawn, and the
    opening hand carries ids 0..handSize-1 in draw order. The sim stores its
    draw-pile top at the END of the list, which is why `ordered_piles` reverses
    that leg.
    """
    c = CombatState(rng=random.Random(0), track_card_ids=True)
    db = c.card_db
    hand_ids = [db.id_of(card) for card in c.player.hand]
    assert hand_ids == list(range(len(c.player.hand)))
    # the card still on top of the draw pile is the next id after the hand
    assert db.id_of(c.player.draw_pile[-1]) == len(c.player.hand)


def test_a_generated_card_is_id_d_when_added_not_when_the_piles_are_walked():
    """The whole point of the port: ids follow ADD order, so a card generated
    into the DRAW pile before the opening draw outranks one added to the HAND
    after it — even though a post-draw walk of hand-then-draw would order them
    the other way round.

    This is the exact 89U act-2 shape. Blessed Antler shuffles 3 Dazed into the
    draw pile at `BeforeHandDraw` (on_player_turn_start), so they take the
    three ids right after the deck while all three are still in the draw pile;
    Vexing Puzzlebox's card is added to the hand at `AfterPlayerTurnStart`
    (on_player_turn_started), after the draw, so it takes the id after those.
    The old reconstruction walked hand-then-draw post-draw instead, which gave
    whichever Dazed got drawn an early id and slid the Puzzlebox card in front
    of its two siblings — and a recorded `PlayCard <puzzlebox id>` then
    resolved to a Dazed.
    """
    from sts2_rl.relics.base import make_relic

    deck_size = 9   # CombatState's default starter deck: 5 Strike + 4 Defend
    c = CombatState(
        rng=random.Random(0), track_card_ids=True,
        relics=[make_relic("blessed_antler"), make_relic("vexing_puzzlebox")],
    )
    db = c.card_db
    generated = [card for card in c.player.all_cards
                 if db.id_of(card) >= deck_size]
    dazed = [card for card in generated if card.id == "dazed"]
    puzzlebox = [card for card in generated if card.id != "dazed"]
    assert len(dazed) == 3 and len(puzzlebox) == 1
    # the three Dazed take the ids right after the deck, in add order …
    assert sorted(db.id_of(card) for card in dazed) == [
        deck_size, deck_size + 1, deck_size + 2]
    # … and the post-draw Puzzlebox card comes after all three, not between
    # them, even though one Dazed was drawn into the hand ahead of it.
    assert db.id_of(puzzlebox[0]) == deck_size + 3


def test_a_direct_pile_mutation_is_picked_up_by_the_refresh_backstop():
    """`refresh` is `OnPileContentsChanged` for the sim sites that still poke a
    pile list directly instead of going through `CardPileCmd` (Giant Rock's
    in-place hand swap)."""
    from sts2_rl.cards.pool import make_card
    c = CombatState(rng=random.Random(0), track_card_ids=True)
    db = c.card_db
    n = len(c.player.all_cards)
    extra = make_card("slimed")
    c.player.discard_pile.append(extra)
    db.refresh(c)
    assert db.id_of(extra) == n                     # next id after the start set


def test_card_ids_are_off_unless_asked_for():
    """Nothing in normal play or RL training resolves a card id; the tracking
    is the replay harness's, and the combat only pays for it on request."""
    assert CombatState(rng=random.Random(0)).card_db is None


def test_a_standalone_db_can_still_be_started_against_a_live_combat():
    """The constructor's `combat` argument and `start_combat` are the same
    entry point (`NetCombatCardDb.StartCombat`); a db built against an
    already-running combat just starts from the state it finds."""
    c = CombatState(rng=random.Random(0))
    db = CombatCardDb(c)
    every = c.player.all_cards
    assert sorted(db.id_of(card) for card in every) == list(range(len(every)))
