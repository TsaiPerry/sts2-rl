"""`TakeRandom` is `UnstableShuffle(rng).Take(n)`, on a NAMED stream (round 7).

`IEnumerableExtensions.cs:17-20`. Two defects per site and both matter: the
wrong stream AND the wrong algorithm. `random.sample` is a partial-selection
algorithm, not a full Fisher-Yates followed by a slice, so it consumes a
different NUMBER of draws in a different order — the stream lands somewhere
else even on the runs where the cards happen to agree.

Queue entries: card/anointed/OnPlay, card/beat_down/OnPlay,
card/discovery/OnPlay, card/distraction/OnPlay, card/splash/OnPlay,
relic/crossbow/AfterSideTurnStart.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.combat_rng import _PARITY_STREAMS


class _Counter(random.Random):
    """A Random that records how many primitive draws it served."""

    def __init__(self, seed):
        super().__init__(seed)
        self.draws = 0

    def random(self):
        self.draws += 1
        return super().random()

    def getrandbits(self, k):
        self.draws += 1
        return super().getrandbits(k)


def _split_streams(cs: CombatState) -> dict[str, _Counter]:
    """Give every named accessor its own Random, so "which stream did this
    site draw on?" is answerable by looking at the counters. In legacy mode
    `CombatRng.legacy` hands the SAME object to all seven, which is exactly
    what makes a wrong-stream bug invisible."""
    counters = {name: _Counter(i) for i, name in enumerate(_PARITY_STREAMS)}
    cs.combat_rng._accessors.update(counters)
    cs._rng = counters["__shared__"] = _Counter(99)
    return counters


def _fresh(deck=None, **kw) -> CombatState:
    return CombatState(rng=random.Random(0), starting_deck=deck, **kw)


def _only(counters: dict[str, _Counter], expected: str) -> None:
    """The site drew on the stream its C# names, and NOT on the shared
    `combat._rng` -- which is the thing `test_rng_tripwire.py` gates on. Other
    named streams may legitimately advance in the same call (Beat Down's
    auto-play picks its target on CombatTargets, CardCmd.cs:77)."""
    used = sorted(n for n, c in counters.items() if c.draws)
    assert expected in used, f"expected {expected!r} to advance, got {used}"
    assert "__shared__" not in used, "drew on the unseeded shared rng"


# ══════════════════════════════════════════════════════════════════════════

def test_anointed_draws_on_combat_card_selection():
    """Anointed.cs:23 — `.Where(Rarity == Rare).TakeRandom(count,
    Rng.CombatCardSelection)`."""
    cs = _fresh()
    rares = [make_card("offering") for _ in range(4)]
    cs.player.draw_pile = rares
    cs.player.hand = []
    counters = _split_streams(cs)
    make_card("anointed").on_play(cs._ctx())
    _only(counters, "card_selection")
    assert len(cs.player.hand) == 4


def test_beat_down_draws_on_the_shuffle_stream():
    """BeatDown.cs:26 — `.ToList().StableShuffle(Rng.Shuffle).Take(3)`. The
    STABILISING SORT comes first (ListExtensions.cs:22-31), so the result no
    longer depends on discard-pile order."""
    cs = _fresh()
    cs.player.discard_pile = [make_card("strike") for _ in range(5)]
    counters = _split_streams(cs)
    make_card("beat_down").on_play(cs._ctx(), target_idx=0)
    _only(counters, "shuffle")


@pytest.mark.parametrize("card_id", ["discovery", "distraction", "splash"])
def test_card_generation_draws_on_combat_card_generation(card_id):
    """`CardFactory.GetDistinctForCombat(..., Rng.CombatCardGeneration)`."""
    cs = _fresh()
    # The choose-a-card screen is a PLAYER choice in C# and costs no RNG; the
    # sim's fallback picks at random, so install a selector to keep the pin on
    # the generation draw alone.
    cs.card_selector = lambda purpose, candidates, count: candidates[:count]
    counters = _split_streams(cs)
    make_card(card_id).on_play(cs._ctx())
    _only(counters, "card_gen")


def test_crossbow_draws_on_combat_card_generation():
    """Crossbow.cs:31 — the relic's own GetDistinctForCombat."""
    relic = make_relic("crossbow")
    cs = _fresh(relics=[relic])
    counters = _split_streams(cs)
    relic.after_side_turn_start(cs.player)
    _only(counters, "card_gen")


# ══════════════════════════════════════════════════════════════════════════
# The algorithm, not just the stream
# ══════════════════════════════════════════════════════════════════════════

def test_take_random_is_a_full_shuffle_then_a_slice():
    """`TakeRandom` = `ToList().UnstableShuffle(rng).Take(count)`
    (IEnumerableExtensions.cs:17-20). A Fisher-Yates over N items takes N-1
    draws NO MATTER how few are taken; `random.sample(pop, 1)` takes one. The
    count is the observable that survives into the stream position."""
    from sts2_rl.cards.pool import take_random

    shuffled = _Counter(0)
    got = take_random(list(range(10)), 1, shuffled)
    assert len(got) == 1

    # A full Fisher-Yates over the same 10 items, for reference.
    reference = _Counter(0)
    reference.shuffle(list(range(10)))
    assert shuffled.draws == reference.draws

    # `sample(pop, 1)` is a different algorithm and costs far less.
    sampled = _Counter(0)
    assert len(sampled.sample(list(range(10)), 1)) == 1
    assert sampled.draws < reference.draws


def test_take_random_does_not_mutate_its_input():
    """`collection.ToList()` — the shuffle is over a COPY."""
    from sts2_rl.cards.pool import take_random

    items = list(range(6))
    take_random(items, 2, random.Random(0))
    assert items == list(range(6))


def test_take_random_takes_everything_when_count_exceeds_the_list():
    """`Take(n)` on a shorter sequence yields the whole thing — there is no
    `min` and no error, which is what lets Anointed pass `10 - handCount`."""
    from sts2_rl.cards.pool import take_random

    assert sorted(take_random([1, 2, 3], 99, random.Random(0))) == [1, 2, 3]
