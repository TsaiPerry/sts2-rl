"""`TakeRandom` is `UnstableShuffle(rng).Take(n)`, on a NAMED stream (round 7).

`IEnumerableExtensions.cs:17-20`. Two defects per site and both matter: the
wrong stream AND the wrong algorithm. `random.sample` is a partial-selection
algorithm, not a full Fisher-Yates followed by a slice, so it consumes a
different NUMBER of draws in a different order — the stream lands somewhere
else even on the runs where the cards happen to agree.

Queue entries: card/anointed/OnPlay, card/beat_down/OnPlay,
card/discovery/OnPlay, card/distraction/OnPlay, card/splash/OnPlay,
relic/crossbow/AfterSideTurnStart, creature_card_cmds/step55 (Entropy's
in-combat transform, `CardCmd.TransformToRandom`).
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd
from sts2_rl.combat_rng import _PARITY_STREAMS
from sts2_rl.rng import RunRngSet


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
# creature_card_cmds/step55 — Entropy's in-combat transform
# ══════════════════════════════════════════════════════════════════════════
#
# EntropyPower.cs:31 — `await CardCmd.TransformToRandom(item,
# player.RunState.Rng.CombatCardSelection)`. `CardCmd.TransformToRandom` is
# also called by six out-of-combat Events (AromaOfChaos, EndlessConveyor,
# MorphicGrove, Symbiote, Trial, WhisperingHollow, all on `base.Rng`) and by
# the New Leaf relic's `AfterObtained` (`RunState.Rng.Niche`) — all of those
# are run-level pickups/events that route through `RunState.transform_card`
# in the sim (run.py), not `CardCmd.transform_to_random` (cmds.py); they are
# out of this seam's scope. Entropy is the only PORTED caller that resolves
# inside a live combat.

def test_entropy_draws_transform_and_selection_on_combat_card_selection():
    """Two draws land on the named stream for one Entropy tick, in PARITY
    mode: which hand card `CardSelectCmd.from_hand`'s selectorless fallback
    picks (wired onto this stream in T3 — combat.py:1185) and what
    `CardCmd.transform_to_random` (cmds.py) turns it into
    (`hooks.combat.combat_rng.card_selection.choice(options)`). Neither draw
    touches the shared legacy `_rng`."""
    cs = CombatState(rng_set=RunRngSet("89U21BV1TZ"))
    cs.player.energy = 10
    cs.player.hand.append(make_card("entropy"))
    assert cs.play_card(len(cs.player.hand) - 1)
    counters = _split_streams(cs)
    cs.end_turn()  # ends the player turn, runs the enemy, starts the next —
    # EntropyPower.on_player_turn_started fires there and does the transform.
    _only(counters, "card_selection")


def test_entropy_legacy_transform_uses_the_identical_shared_rng_object():
    """Legacy mode never touches a game stream at all: `CombatRng.legacy
    (self._rng)` (combat_rng.py:39) aliases EVERY named accessor — including
    card_selection — to the exact object `combat._rng` already was
    (combat.py:158). `transform_to_random`'s roll therefore draws on the
    identical stream a legacy run always used, byte-for-byte, even though the
    call now goes through the named accessor rather than `hooks.combat._rng`
    directly. Regression pin: this identity is what keeps legacy RL
    training/eval sequences unchanged by the step55 fix."""
    cs = _fresh()
    assert cs.combat_rng.card_selection is cs._rng
    cs.player.energy = 10
    cs.player.hand.append(make_card("entropy"))
    assert cs.play_card(len(cs.player.hand) - 1)
    cs.end_turn()  # runs the transform
    assert cs.combat_rng.card_selection is cs._rng  # identity survives it


def test_transform_finds_a_card_that_is_mid_play():
    """CardCmd.cs:391 reads `item.Original.Pile` — whatever pile currently
    holds the card, not a fixed list — so during OnPlay, when that property
    genuinely IS Play, C# transforms a mid-play card exactly like any other,
    and the replacement takes its slot IN PLAY.

    RE-STAGED 2026-08-01 (round 13, R5). The old form parked the card in
    `discard_pile` behind a `_playing_card` marker and concluded from
    `transform_to_random`'s discard branch finding it that "there was no
    Play-pile gap here". That conclusion was an artefact of the stand-in: with
    a real `play_pile` the four-pile scan would have returned None, so the
    fifth branch is what actually makes the claim true."""
    cs = _fresh()
    card = make_card("strike")
    cs.player.play_pile.append(card)
    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, card)
    assert replacement is not None
    assert replacement in cs.player.play_pile
    assert card not in cs.player.play_pile


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
