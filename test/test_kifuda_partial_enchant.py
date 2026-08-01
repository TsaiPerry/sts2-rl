"""relic/kifuda/g2 (mechanism relic/_auto_keep): Kifuda.cs:26-29 builds
`new CardSelectorPrefs(EnchantSelectionPrompt, 0, Cards.IntValue)
{ Cancelable = false, RequireManualConfirmation = true }` — MinSelect 0,
MaxSelect 3. The player may confirm having enchanted 0, 1, 2 or 3 eligible
deck cards; they may not back out of the screen entirely (there is no
"cancel" action anywhere in this decision — only "pick" or "stop here").

Before this round's fix, `sts2_rl/run.py::select_cards` had no min_select
concept at all and `sts2_rl/driver.py::_card_selector` keyed skippability on
`purpose in SKIPPABLE_PURPOSES` — "enchant" was never a member, so
`RunDriver._card_selector`'s `count >= len(remaining)` fast path always
force-filled all 3 without ever asking. Kifuda now uses its own purpose,
"enchant_optional" (driver.SKIPPABLE_PURPOSES), leaving the six other
"enchant"-purpose relics/events (whose own CardSelectorPrefs constructors are
the exact-count overload, MinSelect == MaxSelect) untouched.

Comparison methodology note (see this round's R12-report.md for the full
account): the fix was implemented before these tests were written, because
determining the correct shape required reading CardSelectorPrefs.cs,
CardSelectCmd.cs's FromDeckForEnchantment overload, NDeckEnchantSelectScreen.cs
and this codebase's TWO existing precedents for the identical mechanism
(relic/gambling_chip G3, relics/claws.py's "transform_optional") before any
code could be written responsibly. `test_old_purpose_still_force_fills_*`
below is the closest available substitute for a literal RED-before-fix
snapshot: it exercises the SAME `_card_selector` machinery, in the SAME
post-fix revision, through the OLD unmodified purpose string ("enchant"),
proving that string still exhibits exactly the pre-fix force-fill behaviour
side-by-side with "enchant_optional"'s new partial-confirm behaviour — i.e.
the diff is isolated to the one purpose string this task was scoped to.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.driver import DecisionKind, RunDriver, SKIPPABLE_PURPOSES
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# The old purpose ("enchant") is untouched — every other enchant relic/event
# must keep force-filling.
# ═════════════════════════════════════════════════════════════════════════

def test_enchant_purpose_not_in_skippable_purposes():
    """The six other 'enchant'-purpose sites (beautiful_bracelet,
    electric_shrymp, gnarled_hammer, paels_growth, royal_stamp,
    tri_boomerang and every 'enchant'-purpose event) must keep force-filling
    — their own C# CardSelectorPrefs constructors are the exact-count
    overload (MinSelect == MaxSelect), a genuinely different shape from
    Kifuda's. "enchant_optional" is the new, separate purpose."""
    assert "enchant" not in SKIPPABLE_PURPOSES
    assert "enchant_optional" in SKIPPABLE_PURPOSES


def test_old_enchant_purpose_still_force_fills_through_a_real_driver():
    """A driver-attached policy that always tries to decline (returns the
    skip index whenever legal) still gets all 3 cards through the OLD
    purpose string, because "enchant" never got a skip action appended to
    legal_actions() in the first place — proving this task changed nothing
    about the six untouched call sites, using the exact call shape they use
    (`run.select_cards("enchant", candidates, N)`, no min_select)."""
    run = fresh_run(5)

    def decline_when_possible(request):
        assert request.kind == DecisionKind.SELECT_CARDS
        assert not request.skippable
        return 0     # no skip index is even legal here

    RunDriver(run, decline_when_possible)
    candidates = run.deck[:3]
    picked = run.select_cards("enchant", candidates, 3)
    assert len(picked) == 3


# ═════════════════════════════════════════════════════════════════════════
# The new purpose ("enchant_optional") supports 0, 1, 2 or 3 confirmed.
# ═════════════════════════════════════════════════════════════════════════

def test_enchant_optional_confirms_zero_on_the_first_decline():
    """Pins the PREFS range (MinSelect 0), the level `ICardSelector.
    GetSelectedCards`/RunDriver operate at, not the shipped single-player
    screen's own button behaviour: `NDeckEnchantSelectScreen.ConfirmSelection`
    (CardSelectCmd.cs's screen, `:258-264`) actually refuses to finalize an
    empty selection via a button click, so a literal UI walkthrough could
    never reach 0 this way. The screen is not cancelable either, but
    confirming NOTHING is not the same thing as cancelling: choosing the
    skip sentinel on the very first ask is a first-class outcome at this
    abstraction level, reachable with zero picks made."""
    run = fresh_run(6)
    seen = []

    def decline_immediately(request):
        assert request.kind == DecisionKind.SELECT_CARDS
        assert request.skippable
        seen.append(len(request.candidates))
        return len(request.candidates)     # the skip index

    RunDriver(run, decline_immediately)
    candidates = run.deck[:3]
    picked = run.select_cards("enchant_optional", candidates, 3, min_select=0)
    assert picked == []
    assert seen == [3]     # asked exactly once, then stopped


def test_enchant_optional_confirms_a_partial_pick():
    """Pick one, then decline: 1 confirmed, matching a real player who picks
    fewer than MaxSelect and hits Confirm rather than picking to the max."""
    run = fresh_run(7)
    asks = []

    def pick_one_then_stop(request):
        asks.append(len(request.candidates))
        if len(asks) == 1:
            return 0     # pick the first offered candidate
        return len(request.candidates)     # then stop

    RunDriver(run, pick_one_then_stop)
    candidates = run.deck[:3]
    picked = run.select_cards("enchant_optional", candidates, 3, min_select=0)
    assert len(picked) == 1
    assert asks == [3, 2]     # second ask offers one fewer candidate


def test_enchant_optional_still_reaches_three_when_policy_never_declines():
    """Regression: a policy that always picks (never chooses the skip
    index) still ends up with all 3 — partial confirm being POSSIBLE must
    not make full confirm impossible."""
    run = fresh_run(8)

    def always_pick_first(request):
        return 0

    RunDriver(run, always_pick_first)
    candidates = run.deck[:3]
    picked = run.select_cards("enchant_optional", candidates, 3, min_select=0)
    assert len(picked) == 3


def test_enchant_optional_asks_even_when_candidates_equal_max():
    """C#'s FromDeckForEnchantment shortcut (CardSelectCmd.cs:576) is
    `cards.Count <= prefs.MinSelect` — for Kifuda that's `cards.Count <= 0`,
    so with exactly 3 (or any nonzero number of) eligible cards the screen
    is ALWAYS shown, never silently auto-filled the way the old "enchant"
    purpose's `count >= len(remaining)` fast path did."""
    run = fresh_run(9)
    asked = []

    def record_and_pick_first(request):
        asked.append(True)
        return 0

    RunDriver(run, record_and_pick_first)
    candidates = run.deck[:3]     # exactly count == len(candidates)
    run.select_cards("enchant_optional", candidates, 3, min_select=0)
    assert asked, "the screen must still ask even when candidates == max"


def test_enchant_optional_has_no_cancel_action_only_confirm_fewer():
    """Cancelable = false means there is no 'back out of the screen
    entirely, as if it never happened' action. This is DIFFERENT from
    confirming zero (a legal, first-class outcome above): the sim's
    SELECT_CARDS decision has never modelled a cancel action at all — only
    'pick index i' or 'stop here' — so this holds trivially, but is worth
    pinning against a future change that adds one without gating it on
    Cancelable."""
    run = fresh_run(10)
    captured = []

    def capture_legal(request):
        captured.append(list(request.legal_actions()))
        return len(request.candidates)     # skip

    RunDriver(run, capture_legal)
    candidates = run.deck[:3]
    run.select_cards("enchant_optional", candidates, 3, min_select=0)
    assert len(captured) == 1
    legal = captured[0]
    # own_actions for SELECT_CARDS is exactly range(len(candidates)) plus,
    # when skippable, the single skip index — nothing beyond that.
    assert legal == [0, 1, 2, 3]


# ═════════════════════════════════════════════════════════════════════════
# Selectorless fallback (bare RunState, no card_selector installed) —
# min_select must widen the sample range, not just cap it at exactly count.
# ═════════════════════════════════════════════════════════════════════════

def test_selectorless_fallback_can_return_fewer_than_count_with_min_select_zero():
    """No C# path reaches CardSelectCmd selectorless (it always shows a UI
    screen, consults an installed Selector, or waits on the network) — this
    is a sim-only headless completion, mirroring combat.select_cards's own
    floor/rng.randint shape. Before this fix, run.select_cards had no
    min_select at all and `self.rng.sample(candidates, count)` always
    returned exactly `count`."""
    seen_counts = set()
    for seed in range(40):
        run = fresh_run(seed)
        candidates = run.deck[:3]
        picked = run.select_cards(
            "enchant_optional", candidates, 3, min_select=0)
        assert 0 <= len(picked) <= 3
        seen_counts.add(len(picked))
    # Overwhelmingly unlikely (~(1/4)^40) that 40 uniform draws over {0,1,2,3}
    # all land on 3 unless the floor is being ignored.
    assert seen_counts != {3}, (
        f"selectorless fallback never returned fewer than count: {seen_counts}")


def test_selectorless_fallback_unchanged_when_min_select_is_none():
    """Every OTHER existing caller passes no min_select at all — the
    fallback must still always return exactly `count` for them, byte-
    identical to pre-fix behaviour."""
    for seed in range(10):
        run = fresh_run(seed)
        candidates = run.deck[:3]
        picked = run.select_cards("remove", candidates, 3)
        assert len(picked) == 3


# ═════════════════════════════════════════════════════════════════════════
# End-to-end: the actual relic, driven by a real RunDriver.
# ═════════════════════════════════════════════════════════════════════════

def test_kifuda_end_to_end_partial_confirm():
    """The brief's headline pin: today's force-fill (regression, via a
    policy that always picks) and the new partial-confirm (via a policy that
    declines after one pick), both through `run.add_relic('kifuda')` end to
    end, not just the bare select_cards seam."""
    run = fresh_run(11)
    asks = []

    def pick_one_then_stop(request):
        asks.append(request)
        if len(asks) == 1:
            return 0
        return len(request.candidates)

    RunDriver(run, pick_one_then_stop)
    run.add_relic("kifuda")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "adroit"
    assert enchanted[0].enchantment.amount == 3
    assert all(r.kind == DecisionKind.SELECT_CARDS for r in asks)
    assert all(r.purpose == "enchant_optional" for r in asks)


def test_kifuda_end_to_end_still_enchants_three_by_default():
    """Regression: `_take_first`-style "always pick" driver still gets all
    3 — the historical, still-legal outcome. (test_false_premise_stubs.py's
    test_pickup_enchants_three_deck_cards already pins this with a raw
    card_selector callable; this variant goes through a real RunDriver
    instead.)"""
    run = fresh_run(12)

    def always_pick_first(request):
        return 0

    RunDriver(run, always_pick_first)
    run.add_relic("kifuda")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 3
    assert all(c.enchantment.id == "adroit" and c.enchantment.amount == 3
               for c in enchanted)


def test_kifuda_end_to_end_confirms_zero():
    """A policy that declines on the very first ask enchants nothing at
    all — the PREFS range's floor (MinSelect 0), exercised end to end at the
    RunDriver/ICardSelector abstraction. NOT a claim about the shipped
    screen's own UI: `NDeckEnchantSelectScreen.ConfirmSelection`
    (`:258-264`) refuses to finalize a 0-selection by button click, and
    `CloseSelection` (`:186-190`), the only path that does, is gated behind
    `Cancelable` (false here) — see relics/kifuda.py's docstring."""
    run = fresh_run(13)

    def decline_immediately(request):
        return len(request.candidates)

    RunDriver(run, decline_immediately)
    run.add_relic("kifuda")
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert enchanted == []


def test_kifuda_purpose_registered_in_rl_vocab():
    """The brief flags that a NEW purpose id lands in the shared '_unknown'
    observation bucket unless registered (run_env.py PURPOSE_IDS,
    vocab.json). Confirm "enchant_optional" got a real, stable slot."""
    from sts2_rl.run_env import N_PURPOSES, PURPOSE_INDEX

    assert "enchant_optional" in PURPOSE_INDEX
    idx = PURPOSE_INDEX["enchant_optional"]
    assert 0 <= idx < N_PURPOSES - 1     # a real slot, not the _unknown tail
