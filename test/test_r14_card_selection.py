"""Round 14, lane R7 — the CardSelectorPrefs family (seam/creature_card_cmds
guard25 and its four content sites: potion/ashwater g1, potion/gamblers_brew
g1, relic/gnarled_hammer g3, relic/kifuda AfterObtained).

Root cause (guard25): `driver.SKIPPABLE_PURPOSES` is a lossy re-encoding of
C#'s two `CardSelectorPrefs` integers (MinSelect/MaxSelect) as a frozenset of
purpose strings. `RunDriver._card_selector`'s `count >= len(remaining)` fast
path force-fills UNLESS a call site's purpose is registered there, even when
the call site correctly passes `min_select=0`.

`sts2_rl/combat.py::CombatState.select_cards` (the call-site half) and the
four content sites (`sts2_rl/potions.py`'s Ashwater/Gambler's Brew,
`sts2_rl/cards/neows_fury.py`, `sts2_rl/relics/kifuda.py`) already pass
min_select correctly with their own purpose strings — verified by reading the
tree, not from the brief's prose. `relics/gnarled_hammer.py` did NOT: it
still called `run.select_cards("enchant", candidates, self.CARDS)` with no
min_select, the exact-count shape. This round's fix (in footprint) brings it
to the same "enchant_optional"/min_select=0 shape as kifuda.py.

`driver.py` (home of SKIPPABLE_PURPOSES) is OUT of this lane's footprint this
wave. Its registry is still missing "exhaust_any", "discard_any" and
"from_discard" — the purposes Ashwater, Gambler's Brew and Neow's Fury
actually use — so those three sites remain LIVE force-fills through the real
production RunDriver even though their own call-site code is correct. This
file pins that residual gap so it is not lost; see R7-report.md's
BLOCKED-ON-FOOTPRINT entry for the one-line fix driver.py needs
(`SKIPPABLE_PURPOSES |= {"exhaust_any", "discard_any", "from_discard"}`).
"""
from __future__ import annotations

import random

from sts2_rl.driver import DecisionKind, RunDriver, SKIPPABLE_PURPOSES
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# relic/gnarled_hammer/g3 — FIXED this round (in footprint).
# ═════════════════════════════════════════════════════════════════════════

def test_gnarled_hammer_now_uses_the_optional_shape():
    """GnarledHammer.cs:30-34 builds the identical prefs shape to
    Kifuda.cs:26-29 (MinSelect 0, MaxSelect 3, Cancelable=false,
    RequireManualConfirmation=true). The fix mirrors relics/kifuda.py
    exactly: purpose "enchant_optional", min_select=0."""
    run = fresh_run(20)
    asks = []

    def pick_one_then_stop(request):
        asks.append(request)
        if len(asks) == 1:
            return 0
        return len(request.candidates)     # the skip index

    RunDriver(run, pick_one_then_stop)
    run.add_relic("gnarled_hammer")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "sharp"
    assert enchanted[0].enchantment.amount == 3
    assert all(r.kind == DecisionKind.SELECT_CARDS for r in asks)
    assert all(r.purpose == "enchant_optional" for r in asks)
    assert all(r.skippable for r in asks)


def test_gnarled_hammer_confirms_zero():
    """A policy that declines on the very first ask enchants nothing —
    MinSelect 0's floor, exercised end to end."""
    run = fresh_run(21)

    def decline_immediately(request):
        return len(request.candidates)

    RunDriver(run, decline_immediately)
    run.add_relic("gnarled_hammer")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert enchanted == []


def test_gnarled_hammer_still_enchants_three_by_default():
    """Regression: an always-pick policy still gets all 3 — the historical,
    still-legal outcome (test_false_premise_stubs.py's
    test_pickup_enchants_three_deck_cards already pins this with a raw
    card_selector callable; this is the real-RunDriver variant)."""
    run = fresh_run(22)

    def always_pick_first(request):
        return 0

    RunDriver(run, always_pick_first)
    run.add_relic("gnarled_hammer")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 3


def test_gnarled_hammer_no_longer_shares_the_plain_enchant_purpose():
    """Before this fix, gnarled_hammer force-filled through the shared
    'enchant' purpose exactly like the six untouched exact-count relics/
    events (beautiful_bracelet, electric_shrymp, paels_growth, royal_stamp,
    tri_boomerang, event sites) still correctly do. Confirms the fix moved
    only gnarled_hammer, not that whole family."""
    assert "enchant" not in SKIPPABLE_PURPOSES
    assert "enchant_optional" in SKIPPABLE_PURPOSES


# ═════════════════════════════════════════════════════════════════════════
# R7-F (round 14, wave 2 follow-up): the driver.py registry half is now
# fixed. "exhaust_any" (Ashwater.cs:30), "discard_any" (GamblersBrew.cs:26)
# and "from_discard" (NeowsFury.cs:39) are all MinSelect-0 CardSelectorPrefs
# shapes; SKIPPABLE_PURPOSES now carries all three, so RunDriver._card_selector
# offers a real skip action instead of force-filling. These tests replace the
# BLOCKED-ON-FOOTPRINT pins R7 left (which asserted the broken behaviour) —
# see R7-report.md / R7-review.md / R7-F-report.md for the history.
# ═════════════════════════════════════════════════════════════════════════

def test_exhaust_any_discard_any_from_discard_are_now_registered_skippable():
    """The one-line registry fix the R7 review pinned exactly:
    SKIPPABLE_PURPOSES |= {"exhaust_any", "discard_any", "from_discard"}."""
    assert "exhaust_any" in SKIPPABLE_PURPOSES
    assert "discard_any" in SKIPPABLE_PURPOSES
    assert "from_discard" in SKIPPABLE_PURPOSES


def test_ashwater_can_now_decline_every_card_through_a_real_driver():
    """EXECUTED end-to-end proof the residual live gap is closed: a
    driver-attached policy that always declines when offered a skip action
    now gets the chance to, because "exhaust_any" carries a skip action —
    `request.skippable` is True and the per-index ask loop in
    RunDriver._card_selector lets the policy return the skip index on the
    very first ask."""
    from sts2_rl.driver import RunDriver

    run = RunState(rng=random.Random(1))

    def decline_index(request):
        assert request.kind == DecisionKind.SELECT_CARDS
        if request.skippable:
            return len(request.candidates)
        return 0

    driver = RunDriver(run, decline_index)
    candidates = ["a", "b", "c"]
    picked = driver._card_selector("exhaust_any", candidates, len(candidates))
    assert picked == [], (
        "if this now fails, driver.py's SKIPPABLE_PURPOSES regressed for "
        "exhaust_any -- Ashwater is force-filling again"
    )


def test_gamblers_brew_can_now_decline_every_card_through_a_real_driver():
    """Same shape as Ashwater, for GamblersBrew.cs:26's "discard_any"
    purpose (potions.py:267-275)."""
    from sts2_rl.driver import RunDriver

    run = RunState(rng=random.Random(2))

    def decline_index(request):
        if request.skippable:
            return len(request.candidates)
        return 0

    driver = RunDriver(run, decline_index)
    candidates = ["x", "y"]
    picked = driver._card_selector("discard_any", candidates, len(candidates))
    assert picked == []


def test_neows_fury_can_now_decline_through_a_real_driver():
    """Same shape, for NeowsFury.cs:39's "from_discard" purpose
    (cards/neows_fury.py:66-75). This is the sixth site the R7 report
    flagged (Findings #1) as sharing the same root cause without an
    existing queue record of its own."""
    from sts2_rl.driver import RunDriver

    run = RunState(rng=random.Random(3))

    def decline_index(request):
        if request.skippable:
            return len(request.candidates)
        return 0

    driver = RunDriver(run, decline_index)
    candidates = ["p", "q", "r"]
    picked = driver._card_selector("from_discard", candidates, len(candidates))
    assert picked == []


def test_ashwater_still_takes_all_when_policy_always_picks_first():
    """Regression: an always-pick policy still gets every candidate through
    the per-index ask loop -- the historical, still-legal MaxSelect outcome,
    now reached via the ask loop instead of the force-fill fast path."""
    from sts2_rl.driver import RunDriver

    run = RunState(rng=random.Random(4))
    driver = RunDriver(run, lambda request: 0)
    candidates = ["a", "b", "c"]
    picked = driver._card_selector("exhaust_any", candidates, len(candidates))
    assert picked == candidates


def test_enchant_plain_purpose_still_force_fills_unaffected_by_this_fix():
    """Regression: the six exact-count "enchant" sites (beautiful_bracelet
    etc.) must not have become accidentally skippable -- this fix only
    touched exhaust_any/discard_any/from_discard."""
    assert "enchant" not in SKIPPABLE_PURPOSES
