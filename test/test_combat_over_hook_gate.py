"""`hook_dispatch/G8` — Hook.IterateCombatHookListeners' combat-over gate.

    if (IsOverOrEnding && !IsStarting) yield break;      Hook.cs:55-58

73 of Hook.cs's 147 public dispatchers enumerate through that iterator, so a
dispatch that BEGINS after the combat started ending reaches nobody. 63 more
call `runState.IterateHookListeners` (which never consults the guard), 10
bypass it deliberately — the kill/death/combat-end sequence that has to keep
working while the combat ends — and `ModifyDamage` delegates its walk run-side.

The sim had no gate at all: `combat.py` flips `Phase.COMBAT_OVER` only inside
`_end_combat` and no dispatcher consulted it. The executed witness in the audit
record was Daughter of the Wind still granting its Block from `on_card_played`
after `_all_enemies_dead()` — which is one of the ten deliberate bypasses, so the
LISTENER must still fire. The block itself must not land: `CreatureCmd.GainBlock`
carries its own `IsOverOrEnding` guard (creature_card_cmds G14). Both halves are
pinned below.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.combat import CombatState, Phase
from sts2_rl.hooks import _COMBAT_GATED_HOOKS, HookSystem


class _Spy:
    hook_category = 1

    def __init__(self) -> None:
        self.seen: list[str] = []

    # one gated hook, one run-side hook, one deliberate bypass
    def on_card_drawn(self, card, player=None, from_hand_draw=False):
        self.seen.append("on_card_drawn")          # AfterCardDrawn   (gated)

    def on_combat_end(self):
        self.seen.append("on_combat_end")          # AfterCombatEnd   (run-side)

    def on_card_played(self, card, is_auto_play=False):
        self.seen.append("on_card_played")         # AfterCardPlayed  (bypass)


def _combat_with(spy) -> CombatState:
    cs = CombatState(rng=random.Random(0))
    cs.hooks.register(spy)
    return cs


def test_the_map_only_names_hooks_the_system_dispatches():
    """A typo in `_COMBAT_GATED_HOOKS` would silently gate nothing. Every key
    must be a hook HookSystem actually has a dispatcher for."""
    missing = [h for h in _COMBAT_GATED_HOOKS if not hasattr(HookSystem, h)]
    assert not missing, f"gated names with no dispatcher: {missing}"


def test_the_map_is_the_size_the_census_says():
    """73 guarded C# dispatchers, of which the sim ports these. The count is a
    tripwire: adding a sim hook that maps to a guarded C# one without adding it
    here reopens G8 for that hook silently."""
    assert len(_COMBAT_GATED_HOOKS) == 45
    # Several sim hooks share one C# dispatcher: the two ModifyBlock chains,
    # and the four side hooks the sim splits per side now that the enemy side
    # is side-scoped too (turn_structure G5) — before/after_side_turn_start
    # with before/after_enemy_side_start, on_player_turn_end with
    # before_enemy_side_end, after_player_turn_end with on_enemy_side_end.
    assert len(set(_COMBAT_GATED_HOOKS.values())) == 40


def test_a_gated_hook_reaches_nobody_once_the_combat_is_over():
    spy = _Spy()
    cs = _combat_with(spy)
    cs.hooks.on_card_drawn(None, cs.player)
    assert spy.seen == ["on_card_drawn"]

    cs.phase = Phase.COMBAT_OVER
    spy.seen.clear()
    cs.hooks.on_card_drawn(None, cs.player)
    assert spy.seen == []


@pytest.mark.parametrize("hook,call", [
    ("on_card_played", lambda h, cs: h.on_card_played(None)),
    ("on_combat_end", lambda h, cs: h.on_combat_end()),
])
def test_the_ungated_buckets_still_fire_while_the_combat_ends(hook, call):
    """The ten deliberate bypasses and the 63 run-side dispatchers are how the
    game finishes a kill. Gating them would break combat end itself."""
    spy = _Spy()
    cs = _combat_with(spy)
    cs.phase = Phase.COMBAT_OVER
    call(cs.hooks, cs)
    assert spy.seen == [hook]


def test_daughter_of_the_wind_is_still_DISPATCHED_on_a_lethal_play():
    """The record's executed witness, re-read against the census, then against
    the COMMAND it calls.

    Daughter of the Wind listens on `on_card_played` = `Hook.AfterCardPlayed`,
    one of the ten dispatchers that bypass the hook guard ON PURPOSE
    (Hook.cs:278). So the LISTENER genuinely still runs after a lethal Strike.
    But what it runs is `CreatureCmd.GainBlock` (DaughterOfTheWind.cs:23),
    which opens on `if (IsOverOrEnding) return default` (CreatureCmd.cs:637) —
    so no block lands. The bypass is about dispatch, not about effect, and this
    used to assert the block because only the hook half had been checked.
    """
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("daughter_of_the_wind")])
    seen = []

    class _Watch:
        hook_category = 99                  # after the relics

        def on_block_gained(self, target, amount, card=None):
            seen.append(amount)

    cs.hooks.register(_Watch())
    cs.phase = Phase.COMBAT_OVER
    before = cs.player.block

    cs.hooks.on_card_played(make_card("strike"))
    # Dispatched (the bypass), but the command inside it refused.
    assert cs.player.block == before
    assert seen == []


def test_the_guard_is_read_once_per_dispatch_not_once_per_listener():
    """Hook.cs:55-58 is at the TOP of an iterator method, so it runs when
    enumeration starts. A listener that ends the combat mid-dispatch therefore
    does NOT cut off the listeners after it (Hook.cs step 20)."""
    order: list[str] = []

    class _Ender:
        hook_category = 0        # powers walk before relics

        def on_card_drawn(self, card, player=None, from_hand_draw=False):
            order.append("ender")
            cs.phase = Phase.COMBAT_OVER

    class _After:
        hook_category = 1

        def on_card_drawn(self, card, player=None, from_hand_draw=False):
            order.append("after")

    cs = CombatState(rng=random.Random(0))
    cs.hooks.register(_Ender())
    cs.hooks.register(_After())
    cs.hooks.on_card_drawn(None, cs.player)
    assert order == ["ender", "after"]
    # ...and the NEXT dispatch, which begins after the flip, reaches nobody.
    order.clear()
    cs.hooks.on_card_drawn(None, cs.player)
    assert order == []


def test_before_card_played_is_gated_where_it_was_not():
    """The inverse mismatch the census turned up: `Hook.BeforeCardPlayed`
    (Hook.cs) IS one of the 73, and the sim dispatched it unconditionally."""
    assert _COMBAT_GATED_HOOKS["before_card_played"] == "BeforeCardPlayed"

    played: list[str] = []

    class _Watcher:
        hook_category = 1

        def before_card_played(self, card, target=None):
            played.append("before")

    cs = CombatState(rng=random.Random(0))
    cs.hooks.register(_Watcher())
    cs.hooks.before_card_played(None)
    assert played == ["before"]
    cs.phase = Phase.COMBAT_OVER
    played.clear()
    cs.hooks.before_card_played(None)
    assert played == []


def test_the_gate_is_inert_outside_a_combat():
    """A bare HookSystem (run-level listener walks, previews) has no phase."""
    hooks = HookSystem()
    spy = _Spy()
    hooks.register(spy)
    assert hooks.combat_is_over is False
    hooks.on_card_drawn(None, None)
    assert spy.seen == ["on_card_drawn"]
