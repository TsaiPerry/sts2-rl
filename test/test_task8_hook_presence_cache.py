"""Task 8 follow-up: `HookSystem._has_listener_for`'s presence cache.

Draw-path timing (`_draw` calling the newly-wired `after_card_changed_piles`
on every card, seam/creature_card_cmds guard G8) showed the new dispatch
costing 22.7%-34.8% relative overhead on the sim's hottest loop — well past
the ~5% the task brief flagged as worth a decision. The controller
authorized implementing the proposed fix: `_each()` now skips the
`_ordered()` rebuild + per-listener `getattr` walk entirely for a hook no
CURRENTLY LIVE listener implements, cached by `(hook, self._epoch)` since
`register`/`unregister` are the only two places anywhere in the codebase
that add, remove, or change the liveness of a listener (grepped) and both
already bump `_epoch`.

These tests pin the cache's correctness directly: dispatch semantics must
stay byte-identical to the uncached path whether or not the fast path is
taken, across register/unregister/duplicate-registration/phase-variant
listeners.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.hooks import HookSystem


def fresh() -> CombatState:
    return CombatState(rng=random.Random(0))


class _Listener:
    def __init__(self, log, tag="a"):
        self._log = log
        self._tag = tag

    def probe_hook(self, x):
        self._log.append((self._tag, x))


class _LateListener:
    """Implements only the Late phase variant -- no plain `probe_hook` at
    all -- exactly the shape `_has_listener_for` has to catch across all
    four `_PHASES` suffixes, not just the bare name."""

    def __init__(self, log):
        self._log = log

    def probe_hook_late(self, x):
        self._log.append(("late", x))


def _dispatch(hooks: HookSystem, x):
    """A throwaway dispatcher mirroring the shape of a real HookSystem
    method: `for l, fn in self._each("probe_hook"): fn(x)`."""
    for l, fn in hooks._each("probe_hook"):
        fn(x)


def test_a_hook_with_no_listeners_dispatches_nothing_and_is_reported_absent():
    cs = fresh()
    assert cs.hooks._has_listener_for("probe_hook") is False
    log = []
    _dispatch(cs.hooks, 1)
    assert log == []


def test_registering_a_listener_after_a_cached_absent_result_is_still_seen():
    """The cache must not pin a stale `False` past the register() that
    would flip it -- register() bumps `_epoch`, which is the cache's whole
    invalidation signal."""
    cs = fresh()
    assert cs.hooks._has_listener_for("probe_hook") is False  # populates the cache

    log = []
    listener = _Listener(log)
    cs.hooks.register(listener)

    assert cs.hooks._has_listener_for("probe_hook") is True
    _dispatch(cs.hooks, 2)
    assert log == [("a", 2)]


def test_unregistering_the_last_listener_flips_presence_back_to_false():
    cs = fresh()
    log = []
    listener = _Listener(log)
    cs.hooks.register(listener)
    assert cs.hooks._has_listener_for("probe_hook") is True

    cs.hooks.unregister(listener)
    assert cs.hooks._has_listener_for("probe_hook") is False
    _dispatch(cs.hooks, 3)
    assert log == []


def test_a_duplicate_registration_keeps_presence_true_until_the_last_copy_goes():
    """`unregister`'s own rule: `_listeners` can hold the same object twice;
    only the LAST copy leaving clears the liveness mark. The presence cache
    must agree, since it reads the same `_live` set."""
    cs = fresh()
    log = []
    listener = _Listener(log)
    cs.hooks.register(listener)
    cs.hooks.register(listener)
    assert cs.hooks._has_listener_for("probe_hook") is True

    cs.hooks.unregister(listener)  # one copy gone, one remains
    assert cs.hooks._has_listener_for("probe_hook") is True
    _dispatch(cs.hooks, 4)
    assert log == [("a", 4)]

    cs.hooks.unregister(listener)  # last copy gone
    assert cs.hooks._has_listener_for("probe_hook") is False


def test_a_phase_only_listener_is_detected_and_still_dispatched_to():
    """A listener implementing ONLY `probe_hook_late` (no plain
    `probe_hook`) must still be found by `_has_listener_for` -- it checks
    every _PHASES suffix, not just the bare hook name -- and `_each`'s
    phased branch must still reach it once the fast path lets dispatch
    proceed."""
    cs = fresh()
    log = []
    cs.hooks.register(_LateListener(log))
    assert cs.hooks._has_listener_for("probe_hook") is True

    for l, fn in cs.hooks._each("probe_hook_late"):
        fn(5)
    assert log == [("late", 5)]


def test_dispatch_result_is_identical_with_the_fast_path_forced_off():
    """The cache is a pure optimisation: forcing `_has_listener_for` to
    always return True (i.e. always take the old, uncached walk) must
    produce byte-identical dispatch output to the cached path, for a mix of
    present/absent/phased hooks and register/unregister churn."""
    cs = fresh()
    log_cached = []
    log_uncached = []

    listener = _Listener(log_cached, "x")
    cs.hooks.register(listener)
    cs.hooks.register(_LateListener(log_cached))
    _dispatch(cs.hooks, 10)
    for l, fn in cs.hooks._each("probe_hook_late"):
        fn(11)
    cs.hooks.unregister(listener)
    _dispatch(cs.hooks, 12)  # _LateListener still registered: real path runs

    real = HookSystem._has_listener_for
    try:
        HookSystem._has_listener_for = lambda self, hook: True
        cs2 = fresh()
        listener2 = _Listener(log_uncached, "x")
        cs2.hooks.register(listener2)
        cs2.hooks.register(_LateListener(log_uncached))
        _dispatch(cs2.hooks, 10)
        for l, fn in cs2.hooks._each("probe_hook_late"):
            fn(11)
        cs2.hooks.unregister(listener2)
        _dispatch(cs2.hooks, 12)
    finally:
        HookSystem._has_listener_for = real

    # Not asserting a hand-computed literal here (probe_hook is PHASED once
    # _LateListener is registered, so `_dispatch`'s plain-named call ALSO
    # reaches the late listener) -- the invariant under test is that the
    # cached and uncached paths agree with EACH OTHER, not a hardcoded
    # sequence.
    assert log_cached == log_uncached
    assert log_cached == [("x", 10), ("late", 10), ("late", 11), ("late", 12)]


def test_presence_cache_does_not_break_a_real_draw():
    """Integration check against the actual seam this cache exists for --
    a real `_draw` call, with no combat-pile listener registered, must still
    move the card and fire `on_card_drawn` normally."""
    cs = fresh()
    cs.player.hand.clear()
    from sts2_rl.cards import make_card
    cs.player.draw_pile[:] = [make_card("strike")]
    seen = []
    cs.hooks.register(type("Spy", (), {
        "on_card_drawn": lambda self, card, from_hand_draw=False: seen.append(card.id),
    })())
    cs.player._draw(1)
    assert seen == ["strike"]
    assert len(cs.player.hand) == 1
