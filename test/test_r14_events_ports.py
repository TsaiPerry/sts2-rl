"""
Round 14, lane R5: `event/crystal_sphere` (`IsAllowed`, `g1`) and
`event/war_historian_repy` (`g2`).

Note (R12 update): war_historian_repy's two blockers pinned by R5 have been
FIXED by lane R12 (round 14): the full event body is now ported
(`sts2_rl/events/war_historian_repy.py`) and the new `HistoryCourse` relic was
ported (`sts2_rl/relics/history_course.py`). The two old stub-pinning tests
(`test_war_historian_repy_still_returns_no_options` and
`test_history_course_relic_is_not_ported_anywhere_in_sim`) are now redundant
with `test/test_r14_war_historian.py` (which comprehensively covers the ported
event and relic) and have been removed from this file.

Note (2026-08-01 update): crystal_sphere's two blockers pinned by R5 are now
CLOSED — both legs landed together, as R5 said they had to. The gate is live
(`CrystalSphere.is_allowed`) and the whole payout is ported: the 11x11 grid,
its 15 items and their reveal-order rewards live in
`sts2_rl/events/_crystal_sphere.py`, driven by the automated cell-click rule
the game itself ships for this screen (`CrystalSphereScreenHandler`, the
AutoSlay handler). `test/test_crystal_sphere.py` covers the port; the two old
stub-pinning tests (`test_crystal_sphere_is_allowed_still_hard_stubbed_under_
real_gate` and `test_crystal_sphere_body_is_still_an_empty_stub`) asserted the
deferral itself and have been removed.

R5's core finding survives its own resolution and is still pinned below, since
it is a fact about the ROUTING code rather than about this event: flipping a
shared event's `is_allowed` without giving it a body is never a safe isolated
fix, because `RoomSet.ensure_next_event_is_valid` (sts2_rl/rooms.py:441-458)
treats `is_allowed` as the ONLY gate on routing an event onto a node and has no
fallback for one whose `initial_options()` comes back empty — `Event.begin()`
(sts2_rl/events/base.py:167-176, `_set_state`:319-323) would mark it `finished`
with zero options ever shown. That is why the gate and the minigame had to land
in one change.

Run with:  py -m pytest test/test_r14_events_ports.py -v
"""
from __future__ import annotations

import random

from sts2_rl import RunState, make_event
from sts2_rl.events import ALL_EVENTS
from sts2_rl.events.crystal_sphere import CrystalSphere
from sts2_rl.events.war_historian_repy import WarHistorianRepy
from sts2_rl.rooms import RoomSet
from sts2_rl.cards.event_cards import LanternKeyCard


# ── crystal_sphere ───────────────────────────────────────────────────────

def test_crystal_sphere_gate_and_body_landed_together():
    """The resolution of R5's finding: under the real gate the event is now
    both eligible AND has a body to show. Either half alone would be a
    regression — see the module docstring."""
    run = RunState(rng=random.Random(0), gold=250)
    run.act_index = 1  # act 2 (0-indexed) — CurrentActIndex > 0
    assert CrystalSphere.is_allowed(run) is True
    event = CrystalSphere(run).begin()
    assert event.finished is False
    assert event.option_keys() == ["UNCOVER_FUTURE", "PAYMENT_PLAN"]


def test_crystal_sphere_routing_has_no_fallback_for_an_empty_bodied_event():
    """`RoomSet.ensure_next_event_is_valid` (rooms.py:441-458) only consults
    `is_allowed` when deciding whether a shared event may occupy the next
    event node — it never inspects whether that event actually has content.
    This is the concrete mechanism that makes flipping `is_allowed` alone
    unsafe for ANY event (see module docstring); it outlives crystal_sphere's
    own port."""
    import inspect
    src = inspect.getsource(RoomSet.ensure_next_event_is_valid)
    assert "is_allowed(run)" in src
    # No emptiness / options check anywhere in the routing method.
    assert "initial_options" not in src
    assert "options" not in src


# ── war_historian_repy ───────────────────────────────────────────────────

def test_lantern_key_routes_to_war_historian_repy_in_glory_act():
    """Leg 1 (round 8) is intact: `LanternKeyCard.modify_next_event` still
    redirects to `war_historian_repy` inside the Glory act regardless of
    that event's own `IsAllowed`, which is the reachability leg 2 depends on
    (WarHistorianRepy.cs:29-36 / LanternKey.cs:29-36)."""
    run = RunState(rng=random.Random(0))
    run.act_index = LanternKeyCard.GLORY_ACT_INDEX
    key = LanternKeyCard()
    assert key.modify_next_event(run, "some_other_event") == "war_historian_repy"


def test_war_historian_repy_is_still_registered_for_the_shared_shuffle():
    """Confirms the pool-slot-only registration this stub exists for is
    still intact (SP2 requirement: the 18-id shared shuffle keeps its draw
    count/order even though this event is never surfaced)."""
    assert "war_historian_repy" in ALL_EVENTS
    assert ALL_EVENTS["war_historian_repy"].is_allowed(RunState(rng=random.Random(0))) is False
