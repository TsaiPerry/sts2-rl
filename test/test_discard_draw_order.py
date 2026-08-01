"""Tier-2 Task 10, Mechanisms A + B (seam/creature_card_cmds guards
G11/step49 and G9/step84).

Mechanism A: `PlayerCombatState.discard_hand` mirrors `CombatManager.
FlushPlayerHand` (CombatManager.cs:1313-1347) and NOTHING ELSE -- its only
caller anywhere in the sim is the turn-end flush (`combat.py`'s
`should_flush_hand`/`discard_hand` pair). FlushPlayerHand never fires
`Hook.AfterCardDiscarded`: a repo-wide grep of the decompiled game for
`AfterCardDiscarded` finds exactly four hits -- the AbstractModel/Hook.cs
declarations, the two relic overrides (Tingsha.cs:18, ToughBandages.cs:20),
and its ONE call site, `CardCmd.cs:194`, inside `DiscardAndDraw` (the
explicit "discard these specific cards" command: Concentrate, Sly, Gambler's
Brew, Gambling Chip). The gap-queue's guard G11 / step49 cited
`CardCmd.cs:186-195` as `discard_hand`'s C# counterpart and asked for a
move-then-fire reorder on that premise; `CombatManager.cs`'s real
FlushPlayerHand shows that citation names the wrong method, so the fix here
is removing the `on_card_discarded` call from `discard_hand`, not reordering
it. See scratchpad/task-10-report.md for the full trace.

Mechanism B: `CardPileCmd.Draw` (CardPileCmd.cs:798-857) evaluates
`Hook.ShouldDraw` exactly ONCE, before the per-card loop and before
`drawsRequested`/the hand-space count are even computed. A refusal fires
`Hook.AfterPreventingDraw(modifier)` -- targeted at the ONE listener that
vetoed, mirroring `ShouldDie`/`ShouldClearBlock`'s `out preventer` pattern --
then returns the draw as empty. `PlayerCombatState._draw` used to
re-consult `should_draw` inside the per-card loop and never fired an
`after_preventing_draw` counterpart at all.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import make_card


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


# ══════════════════════════════════════════════════════════════════════════
# Mechanism A -- discard_hand no longer fires on_card_discarded
# ══════════════════════════════════════════════════════════════════════════

class DiscardSpy:
    """Records the card id plus its pile membership AT HOOK TIME -- the
    witness recipe the gap-queue entry (creature_card_cmds/G11) specified: a
    listener that reads pile membership when the hook fires."""

    def __init__(self, player):
        self.player = player
        self.calls: list[tuple[str, bool, bool]] = []

    def on_card_discarded(self, card):
        self.calls.append((
            card.id,
            card in self.player.hand,
            card in self.player.discard_pile,
        ))


class TestMechanismADiscardHandDoesNotFireAfterCardDiscarded:
    def test_flushing_the_hand_fires_on_card_discarded_zero_times(self):
        """Re-executed witness (queue step49/G11): flushing [Strike, Defend]
        used to record `on_card_discarded` for BOTH cards while they were
        still in `hand` and neither had reached `discard_pile` --
        `[('strike', True, False), ('defend', True, False)]` -- the exact
        inversion the gap called out. CombatManager.cs's real FlushPlayerHand
        has no `Hook.AfterCardDiscarded` call anywhere in it (see the module
        docstring), so the C#-faithful result is that the hook fires ZERO
        times here, not twice in the corrected order."""
        cs = fresh()
        p = cs.player
        p.hand.clear()
        p.hand.extend([make_card("strike"), make_card("defend")])
        p.discard_pile.clear()
        spy = DiscardSpy(p)
        cs.hooks.register(spy)

        p.discard_hand()

        assert spy.calls == []
        assert {c.id for c in p.discard_pile} == {"strike", "defend"}
        assert p.hand == []

    def test_retained_cards_are_not_discarded_and_still_fire_nothing(self):
        """Single-turn Retain still partitions the hand correctly (unrelated
        to this mechanism); pins that the fix did not disturb the
        retain/flush split while removing the hook call."""
        cs = fresh()
        p = cs.player
        p.hand.clear()
        kept = make_card("strike")
        kept.give_single_turn_retain()
        flushed = make_card("defend")
        p.hand.extend([kept, flushed])
        p.discard_pile.clear()
        spy = DiscardSpy(p)
        cs.hooks.register(spy)

        p.discard_hand()

        assert spy.calls == []
        assert p.hand == [kept]
        assert flushed in p.discard_pile

    def test_on_card_discarded_still_works_when_something_calls_it_directly(self):
        """Confirms Mechanism A's fix is a removal at the ONE `discard_hand`
        call site, not a break in the hook's plumbing -- `on_card_discarded`
        still dispatches normally when invoked directly, the way the
        DiscardAndDraw-equivalent sim sites do (combat.py's turn-end-in-hand
        path, potions.py's Gambler's Brew, relics/gambling_chip.py -- all
        outside this task's footprint, so exercised here only as a smoke
        check on the dispatcher itself)."""
        cs = fresh()
        spy = DiscardSpy(cs.player)
        cs.hooks.register(spy)
        card = cs.player.hand[0]

        cs.hooks.on_card_discarded(card)

        assert spy.calls == [(card.id, card in cs.player.hand, False)]


# ══════════════════════════════════════════════════════════════════════════
# Mechanism B -- ShouldDraw evaluated once; AfterPreventingDraw on refusal
# ══════════════════════════════════════════════════════════════════════════

class CountingShouldDraw:
    """Always allows the draw; records how many times -- and with what
    `from_hand_draw` value -- it was asked."""

    def __init__(self):
        self.calls: list[bool] = []

    def should_draw(self, player, from_hand_draw):
        self.calls.append(from_hand_draw)
        return True


class VetoingShouldDraw:
    """Blocks the draw and records if/when AfterPreventingDraw reaches it."""

    def __init__(self):
        self.should_draw_calls = 0
        self.after_preventing_draw_calls = 0

    def should_draw(self, player, from_hand_draw):
        self.should_draw_calls += 1
        return False

    def after_preventing_draw(self):
        self.after_preventing_draw_calls += 1


class FlipAfterFirstCall:
    """Allows call #1, refuses every call after -- the mid-draw-flipping
    witness: a listener whose answer depends on how many times it has
    already been asked THIS call, which is the one shape that makes a
    once-only evaluation and a per-card re-evaluation actually disagree.
    Every ported should_draw listener (Fiddle, NoDrawPower) is stateless and
    can never produce this divergence, which is why the bug stayed dormant."""

    def __init__(self):
        self.calls = 0

    def should_draw(self, player, from_hand_draw):
        self.calls += 1
        return self.calls == 1


def _five_strikes_draw_pile(cs: CombatState) -> None:
    cs.player.draw_pile.clear()
    cs.player.draw_pile.extend(make_card("strike") for _ in range(5))
    cs.player.hand.clear()


class TestMechanismBShouldDrawEvaluatedOnce:
    def test_should_draw_is_consulted_once_for_a_multi_card_draw(self):
        """Re-executed witness (queue step84/G9): drawing 5 cards used to
        call `should_draw` 5 times (once per card, inside the loop); C#'s
        `CardPileCmd.Draw` calls `Hook.ShouldDraw` exactly once per Draw
        call, before the loop even starts."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        spy = CountingShouldDraw()
        cs.hooks.register(spy)

        cs.player._draw(5)

        assert len(spy.calls) == 1
        assert len(cs.player.hand) == 5

    def test_should_draw_receives_from_hand_draw_once_up_front(self):
        """The single evaluation still carries C#'s `fromHandDraw` argument
        (Fiddle keys its whole veto on it)."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        spy = CountingShouldDraw()
        cs.hooks.register(spy)

        cs.player._draw(5, from_hand_draw=True)

        assert spy.calls == [True]

    def test_a_refusal_draws_zero_cards_not_a_partial_hand(self):
        """An ALWAYS-refusing listener draws zero cards under EITHER the old
        per-card loop or today's hoisted check -- the two are behaviorally
        identical here, because the old loop's very first `should_draw` call
        is also its first refusal, so it never gets far enough for a later
        card to matter. What this actually pins is narrower: `should_draw`
        is asked exactly ONCE (not once per would-be card) and the draw is
        refused wholesale (`Array.Empty<CardModel>()`-shaped: zero cards, not
        "however many happened to be checked before the veto"). The real
        old-vs-new DIVERGENCE -- a listener whose answer changes partway
        through what would have been a multi-card draw -- is
        `test_a_mid_draw_flipping_listener_sees_the_once_only_evaluation`,
        below."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        veto = VetoingShouldDraw()
        cs.hooks.register(veto)

        cs.player._draw(5)

        assert cs.player.hand == []
        assert len(cs.player.draw_pile) == 5
        assert veto.should_draw_calls == 1

    def test_a_mid_draw_flipping_listener_sees_the_once_only_evaluation(self):
        """The brief's own witness recipe: a `should_draw` listener that
        allows the first call and refuses every call after. Hoisted (today's
        code): `should_draw` is asked once, gets True, and the WHOLE 5-card
        draw proceeds untouched -- hand size 5, exactly 1 call. The OLD
        per-card loop would have asked again before the second card, gotten
        False, and stopped -- hand size 1, 2 calls. This is the case that
        actually distinguishes the two implementations; no ported listener
        (Fiddle, NoDrawPower) is stateful enough to produce it, which is why
        the mechanism was dormant despite the bug."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        flip = FlipAfterFirstCall()
        cs.hooks.register(flip)

        cs.player._draw(5)

        assert len(cs.player.hand) == 5
        assert flip.calls == 1

    def test_after_preventing_draw_fires_on_refusal(self):
        """CardPileCmd.cs:806 -- the refusal branch fires
        Hook.AfterPreventingDraw(modifier) before returning."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        veto = VetoingShouldDraw()
        cs.hooks.register(veto)

        cs.player._draw(5)

        assert veto.after_preventing_draw_calls == 1

    def test_after_preventing_draw_is_targeted_not_broadcast(self):
        """Hook.AfterPreventingDraw takes the specific `modifier` ShouldDraw
        named `out` -- it is not a broadcast to every should_draw listener.
        A second, non-vetoing should_draw listener must not receive it, and
        the dispatcher must not blow up reaching a listener with no
        `after_preventing_draw` method at all (it has none, matching
        NoDrawPower, which implements only `should_draw`)."""
        cs = fresh()
        _five_strikes_draw_pile(cs)
        veto = VetoingShouldDraw()
        allow = CountingShouldDraw()
        cs.hooks.register(allow)
        cs.hooks.register(veto)

        cs.player._draw(5)

        assert veto.after_preventing_draw_calls == 1
        assert not hasattr(allow, "after_preventing_draw")

    def test_should_draw_still_fires_once_when_the_hand_is_already_full(self):
        """CardPileCmd.cs:800-808 runs `IsOverOrEnding` then `ShouldDraw`
        strictly BEFORE `num` (hand space) is computed -- so ShouldDraw is
        consulted even when the hand is already full; only the per-card loop
        that follows is what a full hand short-circuits (`num == 0` at
        CardPileCmd.cs:818-823, mirrored by `_draw`'s own
        `len(hand) >= MAX_HAND_SIZE` check inside the loop). This pins that
        ShouldDraw fires regardless."""
        cs = fresh()
        cs.player.draw_pile.clear()
        cs.player.draw_pile.extend(make_card("strike") for _ in range(3))
        cs.player.hand.clear()
        cs.player.hand.extend(make_card("defend") for _ in range(cs.player.MAX_HAND_SIZE))
        spy = CountingShouldDraw()
        cs.hooks.register(spy)

        cs.player._draw(3)

        assert len(spy.calls) == 1
        assert len(cs.player.hand) == cs.player.MAX_HAND_SIZE  # nothing drawn

    def test_fiddle_and_no_draw_power_are_the_only_ported_should_draw_listeners(self):
        """Enumeration for the report: Fiddle (relics/fiddle.py) and
        NoDrawPower (sts2_rl.powers) are the only two ported `should_draw`
        listeners -- matching C#'s two overrides exactly (Fiddle.cs,
        NoDrawPower.cs). Neither is stateful across a single `_draw` call,
        which is why this mechanism stayed dormant even before today's fix.

        Neither currently implements `after_preventing_draw` in the sim: C#'s
        sole implementer, Fiddle.cs:41-45, is Flash()-only VFX with no
        gameplay effect, so the port never carried it over -- a separate,
        presentation-only, out-of-footprint gap this task does not close (see
        the report)."""
        from sts2_rl.powers import NoDrawPower
        from sts2_rl.relics.fiddle import Fiddle

        assert hasattr(Fiddle, "should_draw")
        assert hasattr(NoDrawPower, "should_draw")
        assert not hasattr(Fiddle, "after_preventing_draw")
        assert not hasattr(NoDrawPower, "after_preventing_draw")
