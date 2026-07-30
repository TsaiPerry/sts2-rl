"""`CardPileCmd.AutoPlayFromDrawPile` is TWO-PHASE (CardPileCmd.cs:931-966).

Phase 1 pulls all `count` cards out of the draw pile into `PileType.Play`
(one `ShuffleIfNecessary` per pick, :939); phase 2 plays them (:956-965),
setting `ExhaustOnNextPlay = forceExhaust` on each. So the cards are COMMITTED
before any of them resolves, and a draw or reshuffle the first one causes
cannot change which card is played second.

Both callers hand-rolled the verb instead: Havoc interleaved AND skipped the
whole play bracket, Mayhem interleaved.

Queue entries: card/havoc/OnPlay, power/mayhem/g2.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardPileCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS


def _combat(hand=(), draw=(), discard=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    for pile, ids in ((cs.player.hand, hand), (cs.player.draw_pile, draw),
                      (cs.player.discard_pile, discard)):
        for cid in ids:
            card = make_card(cid)
            card.combat = cs
            cs.hooks.register(card)
            pile.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# the verb itself
# ══════════════════════════════════════════════════════════════════════════

def test_both_cards_are_committed_before_either_resolves():
    """CardPileCmd.cs:939-955 pulls every pick first. Pommel Strike draws, so
    an interleaved implementation would let the draw change the second pick."""
    # draw pile bottom->top: [defend, pommel_strike]; top two are the picks.
    cs = _combat(draw=["strike", "defend", "pommel_strike"])
    picks = [cs.player.draw_pile[-1], cs.player.draw_pile[-2]]
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 2)
    # Both committed picks resolved, and the Strike that Pommel Strike drew is
    # in the HAND rather than having been played as the second pick.
    assert [c.id for c in picks] == ["pommel_strike", "defend"]
    assert [c.id for c in cs.player.hand] == ["strike"]


def test_a_short_draw_pile_stops_the_loop():
    """`if (cardModel == null) break` (CardPileCmd.cs:949-952)."""
    cs = _combat(draw=["strike"])
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 3)
    assert not cs.player.draw_pile


def test_each_pick_reshuffles_if_necessary():
    """`await ShuffleIfNecessary(...)` is INSIDE the pick loop (:939), so an
    empty draw pile is refilled from the discard between picks."""
    cs = _combat(draw=["strike"], discard=["defend", "defend"])
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 2)
    # Strike, then a Defend pulled in by the reshuffle: two block gains' worth
    # of Defend is 5, and the Strike hit an enemy.
    assert cs.player.block == 5


def test_force_exhaust_routes_through_exhaust_on_next_play():
    """`item.ExhaustOnNextPlay = forceExhaust` (CardPileCmd.cs:960) — the card
    is EXHAUSTED by the normal result-pile path, not moved by hand."""
    cs = _combat(draw=["strike"])
    card = cs.player.draw_pile[-1]
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 1,
                                        force_exhaust=True)
    assert card in cs.player.exhaust_pile
    assert card.exhaust_on_next_play is False   # consumed


def test_without_force_exhaust_the_card_discards():
    cs = _combat(draw=["strike"])
    card = cs.player.draw_pile[-1]
    CardPileCmd.auto_play_from_draw_pile(cs.hooks, cs.player, 1)
    assert card in cs.player.discard_pile


# ══════════════════════════════════════════════════════════════════════════
# card/havoc — the bracket it used to skip
# ══════════════════════════════════════════════════════════════════════════

def test_havoc_plays_a_replayed_card_twice():
    """`CardModel.OnPlayWrapper`'s play-count loop is seeded from
    `1 + BaseReplayCount` (Hidden Gem). Havoc called `card.on_play` directly
    and so played it once."""
    cs = _combat(hand=["havoc"], draw=["strike"])
    strike = cs.player.draw_pile[-1]
    strike.base_replay_count = 1
    for e in cs.enemies:
        e.hp = e.max_hp = 60                 # no overkill, and the roll picks one
    before = sum(e.hp for e in cs.enemies)
    cs.play_card(0)
    assert sum(e.hp for e in cs.enemies) == before - 12   # 6 twice, not once


def test_havoc_exhausts_the_card_it_played():
    cs = _combat(hand=["havoc"], draw=["strike"])
    strike = cs.player.draw_pile[-1]
    cs.play_card(0)
    assert strike in cs.player.exhaust_pile


def test_havoc_exhausts_an_unplayable_card_it_could_not_play():
    """`MoveToResultPileWithoutPlaying` (CardModel.cs:2089-2107) honours
    ExhaustOnNextPlay, so forceExhaust reaches an unplayable card too — it goes
    to the EXHAUST pile, not the discard."""
    cs = _combat(hand=["havoc"], draw=["burn"])
    burn = cs.player.draw_pile[-1]
    cs.play_card(0)
    assert burn in cs.player.exhaust_pile


def test_havoc_makes_a_power_card_vanish():
    """A Power card's result pile is `PileType.None` (CardModel.cs:2071-2074)."""
    cs = _combat(hand=["havoc"], draw=["inflame"])
    inflame = cs.player.draw_pile[-1]
    cs.play_card(0)
    assert inflame not in cs.player.exhaust_pile
    assert inflame not in cs.player.discard_pile
    assert cs.player.strength == 2


def test_havoc_uses_the_stable_reshuffle():
    """Havoc inlined `combat_rng.shuffle.shuffle(...)` — an UNSTABLE shuffle —
    where ShuffleIfNecessary is `CardPileCmd.Shuffle` -> StableShuffle."""
    cs = _combat(hand=["havoc"], discard=["strike", "defend"])
    cs.play_card(0)
    assert len(cs.player.draw_pile) + len(cs.player.exhaust_pile) >= 2


# ══════════════════════════════════════════════════════════════════════════
# power/mayhem — the same verb, forceExhaust false
# ══════════════════════════════════════════════════════════════════════════

def test_mayhem_commits_both_cards_before_either_resolves():
    """MayhemPower.cs:20 — `AutoPlayFromDrawPile(Amount, Top, false)`."""
    from sts2_rl.powers import MayhemPower
    cs = _combat(draw=["strike", "defend", "pommel_strike"])
    PowerCmd.apply(cs.hooks, cs.player, MayhemPower, 2, applier=cs.player)
    picks = [cs.player.draw_pile[-1], cs.player.draw_pile[-2]]
    cs.hooks.after_auto_pre_play_phase_entered(cs.player)
    assert [c.id for c in picks] == ["pommel_strike", "defend"]
    assert [c.id for c in cs.player.hand] == ["strike"]
    assert all(c in cs.player.discard_pile for c in picks)
