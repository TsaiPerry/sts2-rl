# test/test_combat_card_db.py
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.combat_card_db import CombatCardDb


def test_ids_are_contiguous_over_allpiles_order():
    c = CombatState(rng=random.Random(0))
    db = CombatCardDb()
    db.start(c)
    every = (c.player.hand + c.player.draw_pile
             + c.player.discard_pile + c.player.exhaust_pile)
    ids = sorted(db.id_of(card) for card in every)
    assert ids == list(range(len(every)))          # 0..N-1, no gaps
    # round-trips
    for card in every:
        assert db.get(db.id_of(card)) is card


def test_new_card_gets_next_id_on_refresh():
    from sts2_rl.cards.pool import make_card
    c = CombatState(rng=random.Random(0))
    db = CombatCardDb()
    db.start(c)
    n = len(c.player.all_cards)
    extra = make_card("slimed")
    c.player.discard_pile.append(extra)
    db.refresh(c)
    assert db.id_of(extra) == n                     # next id after the start set
