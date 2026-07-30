"""`History.CardPlaysStarted` is a SECOND list, not the one the sim had.

`CombatHistory.cs:26/28` exposes CardPlaysStarted and CardPlaysFinished
separately, and `CardModel.OnPlayWrapper` pushes them at two different points
inside the replay loop: `CardPlayStarted` at CardModel.cs:1930, immediately
after Hook.BeforeCardPlayed and BEFORE `await OnPlay`, and `CardPlayFinished`
at :1956, after the enchantment and affliction have resolved. The sim had one
entry recorded at the FINISHED position, so a card auto-played from inside
another card's OnPlay could not see the outer play.

Queue entries: power/nostalgia/g4, card/normality/ShouldPlay.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.history import CardPlayedEntry, CardPlayStartedEntry
from sts2_rl.powers import NostalgiaPower


def _combat(hand=(), draw=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)])
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    for cid in hand:
        cs.player.hand.append(make_card(cid))
    for cid in draw:
        cs.player.draw_pile.append(make_card(cid))
    for card in cs.player.hand + cs.player.draw_pile:
        card.combat = cs
        cs.hooks.register(card)
    return cs


def test_a_started_row_exists_and_precedes_the_finished_row():
    """CardModel.cs:1930 vs :1956 — started is pushed before OnPlay runs."""
    cs = _combat(hand=["strike"])
    cs.play_card(0, target_idx=0)
    kinds = [type(e).__name__ for e in cs.history.entries
             if isinstance(e, (CardPlayStartedEntry, CardPlayedEntry))]
    assert kinds == ["CardPlayStartedEntry", "CardPlayedEntry"]


def test_the_started_row_is_visible_from_inside_on_play():
    """The whole point: the row is pushed at :1930 and OnPlay is :1931, so a
    card's own OnPlay already sees its own started row — which is what lets an
    inner auto-play see the outer one."""
    from sts2_rl.cards.base import Card, CardType, TargetType

    seen: list[int] = []

    class Probe(Card):
        id = "test_probe_started"
        name = "Probe"
        card_type = CardType.SKILL
        target_type = TargetType.SELF

        def _init_vars(self) -> None:
            self._energy_cost = 0

        def on_play(self, ctx, target_idx=None) -> None:
            seen.append(sum(1 for _ in cs.history.of_type(CardPlayStartedEntry)))

    cs = _combat()
    probe = Probe()
    probe.combat = cs
    cs.hooks.register(probe)
    cs.player.hand.append(probe)
    cs.play_card(0)
    assert seen == [1]


def test_nostalgia_counts_the_outer_play_when_deciding_the_inner_card():
    """NostalgiaPower.cs:31-42 counts CardPlaysStarted. With Nostalgia 1, a
    Cascade that auto-plays a Strike: the OUTER Cascade is already counted when
    the inner Strike's result pile is decided, so `num = 1 >= Amount = 1` and
    the Strike goes to the DISCARD. Only Cascade is redirected."""
    cs = _combat(hand=["cascade"], draw=["strike"])
    from sts2_rl.cmds import PowerCmd
    PowerCmd.apply(cs.hooks, cs.player, NostalgiaPower, 1, applier=cs.player)
    cs.play_card(0, target_idx=0)
    assert [c.id for c in cs.player.draw_pile] == ["cascade"]
    assert [c.id for c in cs.player.discard_pile] == ["strike"]


def test_normality_blocks_the_fourth_play_counting_started_plays():
    """Normality.cs:33 counts CardPlaysStarted, and ShouldPlay is consulted by
    both CardModel.CanPlay (CardModel.cs:1755) and CardCmd.AutoPlay
    (CardCmd.cs:64). Play two cards, then a third that auto-plays a fourth:
    when the auto-play is tested there are THREE started plays, so it is
    blocked."""
    cs = _combat(hand=["strike", "strike", "cascade", "normality"],
                 draw=["strike"])
    assert cs.play_card(0, target_idx=0)
    assert cs.play_card(0, target_idx=0)
    inner = cs.player.draw_pile[0]
    assert cs.play_card(0, target_idx=0)          # Cascade, the third play
    # The auto-played Strike was blocked, so it never resolved: no started row
    # for it, and it went to its result pile unplayed.
    started = [e.card for e in cs.history.of_type(CardPlayStartedEntry)]
    assert inner not in started
    assert len(started) == 3


def test_normality_allows_the_third_play():
    cs = _combat(hand=["strike", "strike", "strike", "normality"])
    assert cs.play_card(0, target_idx=0)
    assert cs.play_card(0, target_idx=0)
    assert cs.play_card(0, target_idx=0)
    assert len(list(cs.history.of_type(CardPlayStartedEntry))) == 3


def test_normality_does_not_block_while_it_sits_outside_the_hand():
    """Normality.cs:46-50 — `Pile == null || Pile.Type != PileType.Hand`."""
    cs = _combat(hand=["strike", "strike", "strike"])
    normality = make_card("normality")
    normality.combat = cs
    cs.hooks.register(normality)
    cs.player.draw_pile.append(normality)
    for _ in range(3):
        assert cs.play_card(0, target_idx=0)
    assert cs.hooks.should_play_card(make_card("strike")) is True


def test_a_replayed_card_pushes_one_started_row_per_iteration():
    """The started push is INSIDE the replay loop (CardModel.cs:1904-1930), so
    a Hidden-Gem'd card advances the count by its play count."""
    cs = _combat(hand=["strike"])
    cs.player.hand[0].base_replay_count = 1
    cs.play_card(0, target_idx=0)
    assert len(list(cs.history.of_type(CardPlayStartedEntry))) == 2
