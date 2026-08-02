"""Task 20 -- `creature_card_cmds/G7` (exhaust knows only two piles),
`/G13` + `/step8` (escape leaves powers registered), and `/step69`
(AfterCardChangedPiles at RemoveFromCombat).

Run with:  py -m pytest test/test_exhaust_escape_removal.py -v

## A. G7 -- ExhaustCmd.exhaust only knew about hand/discard

`CardPileCmd.Add(card, PileType.Exhaust, Bottom)`'s `RemoveFromCurrentPile()`
(CardPileCmd.cs:496) is pile-agnostic -- it removes the card from WHATEVER
pile it currently sits in, not just hand/discard. The sim's old
`ExhaustCmd.exhaust` only checked hand/discard, so a draw-pile card ended up
in two piles at once, and a card already in the exhaust pile, exhausted
again, duplicated the same instance. `CardPile.AddInternal` does throw if the
target pile already holds the instance (CardPile.cs:86-89) -- that is
creature_card_cmds/N4's invariant on the three pile-ADD helpers -- but it is
NOT reachable on this path, because `CardPileCmd.Add` empties the card's old
slot first (see the re-exhaust test below). Fixed: exhaust now scans for the
card's CURRENT pile -- INCLUDING the exhaust pile, where a re-exhaust is a
legal no-throw reposition to the bottom, not an error (CardPileCmd.cs:364,
:494-496, :510 remove BEFORE they add).

## B. G13 + step8 -- escape left the escaper's powers registered

`CreatureCmd.Escape` (CreatureCmd.cs:579-603) calls
`creature.RemoveAllPowersInternalExcept()` (:589), which strips EVERY power
via `PowerModel.RemoveInternal` (Creature.cs:658-666) -- silently, with NO
`AfterRemoved` awaited. This is the deliberate contrast with death
(CreatureCmd.cs:533-537, which awaits `AfterRemoved` per stripped power).
The sim's escape used to leave every power on the creature and registered as
a live hook listener. Fixed: escape now unregisters and detaches every
power (mirroring `Power._expire()`, the sim's own no-`on_removed` primitive,
already used by `PowerCmd.modify_amount`'s duration-tick expiry) with no
`on_removed` call, while death (`_strip_powers_after_death`) is unchanged
and still calls `on_removed` for each stripped power.

## C. step69 -- RemoveFromCombat's AfterCardChangedPiles was never dispatched

T8 wired three of the four C# `AfterCardChangedPiles` dispatch sites
(Add, Draw, the two reshuffle helpers) and explicitly left `RemoveFromCombat`
(CardPileCmd.cs:188) for this task, because its one sim site --
`monsters/hive/thieving_hopper.py`'s `_thievery` -- was out of T8's
footprint. `CardPileCmd.cs:188` fires `Hook.AfterCardChangedPiles` with the
OLD/leaving pile (`cardPile2.Type`) and a `null` `clonedBy`, matching every
other wired site's `(card, pile, cloned_by)` argument shape
(`hooks.after_card_changed_piles`, hooks.py:995-1042).
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, CreatureCmd, Power, PowerType
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardPileCmd, EnergyCmd, ExhaustCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.hive import ThievingHopper
from sts2_rl.powers import BattlewornDummyTimeLimitPower


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


class _RecordingPower(Power):
    """A power whose `on_removed` (the sim's `AfterRemoved` mirror) records
    that it fired, so a test can tell "stripped silently" from "stripped
    with AfterRemoved awaited" apart."""

    id = "recording_test_power"
    name = "Recording"
    power_type = PowerType.BUFF

    def __init__(self, owner, amount, hooks, applier=None):
        super().__init__(owner, amount, hooks, applier)
        self.removed = False

    def on_removed(self, owner) -> None:
        self.removed = True


class _PileChangeRecorder:
    """A bare `after_card_changed_piles` listener with no other hook
    implemented -- mirrors the plain listener pattern test_hook_order.py
    uses for `modify_energy_gain` (`NegatingListener`)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def after_card_changed_piles(self, card, pile, cloned_by) -> None:
        self.calls.append((card, pile, cloned_by))


# ═════════════════════════════════════════════════════════════════════════
# A. creature_card_cmds/G7 -- exhaust is pile-agnostic, invariant-guarded
# ═════════════════════════════════════════════════════════════════════════

class TestExhaustIsPileAgnostic:
    def test_a_draw_pile_card_is_removed_from_the_draw_pile_when_exhausted(self):
        """Old bug: ExhaustCmd.exhaust only checked hand/discard, so a
        draw-pile card stayed in draw_pile AND was appended to exhaust_pile
        -- the same instance in two piles at once."""
        cs = fresh()
        card = make_card("strike")
        cs.player.draw_pile.clear()
        cs.player.draw_pile.append(card)

        ExhaustCmd.exhaust(cs.hooks, cs.player, card)

        assert card not in cs.player.draw_pile
        assert cs.player.exhaust_pile.count(card) == 1
        assert len(cs.player.draw_pile) == 0

    def test_a_discard_pile_card_is_still_removed_from_discard(self):
        """Sanity: the pre-existing, already-correct half of the fix is
        unaffected by generalising it to every pile."""
        cs = fresh()
        card = make_card("strike")
        cs.player.discard_pile.append(card)

        ExhaustCmd.exhaust(cs.hooks, cs.player, card)

        assert card not in cs.player.discard_pile
        assert cs.player.exhaust_pile.count(card) == 1

    def test_a_hand_card_is_still_removed_from_hand(self):
        cs = fresh()
        card = cs.player.hand[0]

        ExhaustCmd.exhaust(cs.hooks, cs.player, card)

        assert card not in cs.player.hand
        assert cs.player.exhaust_pile.count(card) == 1

    def test_exhausting_an_already_exhausted_card_repositions_it_without_raising(self):
        """Two bugs bracket this case, and the RIGHT answer is neither.

        The original bug silently grew exhaust_pile to hold the same object
        twice. Task 20's first fix over-corrected, asserting the card was
        absent from the exhaust pile before appending, so the sim RAISED where
        the game performs a legal move.

        `CardPileCmd.Add` captures `oldPile = card.Pile` (CardPileCmd.cs:364)
        and calls `card.RemoveFromCurrentPile(...)` at :494-496 BEFORE
        `targetPile.AddInternal(...)` at :510. With
        `oldPile == targetPile == Exhaust` the card is removed first, so
        `AddInternal`'s `Cards.Contains` guard (CardPile.cs:86-89) tests an
        already-emptied slot and never throws. Net C# behavior: a no-throw
        reposition to the bottom of the exhaust pile.
        """
        cs = fresh()
        card = make_card("strike")
        other = make_card("defend")
        cs.player.exhaust_pile.extend([card, other])

        ExhaustCmd.exhaust(cs.hooks, cs.player, card)

        assert cs.player.exhaust_pile.count(card) == 1  # not duplicated
        # ...and it moved to the BOTTOM, which is what remove-then-add does.
        assert cs.player.exhaust_pile == [other, card]


# ═════════════════════════════════════════════════════════════════════════
# B. creature_card_cmds/G13 + step8 -- escape strips powers silently
# ═════════════════════════════════════════════════════════════════════════

class TestEscapeStripsPowersSilently:
    def test_an_escaped_creatures_power_is_unregistered_and_detached(self):
        cs = fresh()
        enemy = cs.enemy
        power = _RecordingPower(enemy, 1, cs.hooks)
        enemy.powers.add(power)
        cs.hooks.register(power)

        CreatureCmd.escape(cs.hooks, enemy)

        assert enemy.escaped
        assert "recording_test_power" not in enemy.powers
        assert power not in cs.hooks._listeners

    def test_escape_does_not_call_on_removed(self):
        """The whole point of G13: C# strips via RemoveInternal, which skips
        AfterRemoved entirely -- the deliberate contrast with death."""
        cs = fresh()
        enemy = cs.enemy
        power = _RecordingPower(enemy, 1, cs.hooks)
        enemy.powers.add(power)
        cs.hooks.register(power)

        CreatureCmd.escape(cs.hooks, enemy)

        assert power.removed is False

    def test_death_still_calls_on_removed_for_contrast(self):
        """Same power, same setup, but killed instead of escaped: C#'s death
        arm awaits AfterRemoved per stripped power (CreatureCmd.cs:533-537)
        and the sim already does this via `_strip_powers_after_death`."""
        cs = fresh()
        enemy = cs.enemy
        power = _RecordingPower(enemy, 1, cs.hooks)
        enemy.powers.add(power)
        cs.hooks.register(power)

        CreatureCmd.kill(cs.hooks, enemy)

        assert power.removed is True
        assert "recording_test_power" not in enemy.powers

    def test_a_power_that_escapes_its_own_owner_from_within_its_own_hook_survives_the_strip(self):
        """BattlewornDummyTimeLimitPower.on_enemy_side_end calls
        CreatureCmd.escape on its OWN owner from inside its own hook method
        -- the power being stripped is the very listener whose method is on
        the call stack. The strip must snapshot creature.powers before
        mutating (mirroring _strip_powers_after_death's own snapshot-then-
        mutate pattern) rather than crash or corrupt hook dispatch."""
        cs = fresh()
        dummy = cs.enemy
        from sts2_rl.cmds import PowerCmd
        PowerCmd.apply(cs.hooks, dummy, BattlewornDummyTimeLimitPower, 1)

        dummy.powers["battleworn_dummy_time_limit"].on_enemy_side_end()

        assert dummy.escaped
        assert "battleworn_dummy_time_limit" not in dummy.powers

    def test_retained_corpse_machinery_is_untouched_by_the_escape_strip(self):
        """Brief warning: a dead-but-retained creature (Decimillipede
        segment) must not be touched by the escape code path at all --
        escape's entry guard (`if creature.is_dead: return`) is unchanged
        and short-circuits before any stripping runs, exactly like C#'s own
        `if (creature.IsDead) return`."""
        cs = fresh()
        enemy = cs.enemy
        power = _RecordingPower(enemy, 1, cs.hooks)
        enemy.powers.add(power)
        cs.hooks.register(power)
        enemy.hp = 0
        enemy.retained_after_death = True  # withered-but-kept, like Decimillipede

        CreatureCmd.escape(cs.hooks, enemy)

        assert not enemy.escaped               # escape refused: creature.is_dead
        assert "recording_test_power" in enemy.powers   # untouched
        assert power.removed is False


# ═════════════════════════════════════════════════════════════════════════
# C. creature_card_cmds/step69 -- RemoveFromCombat dispatches
#    AfterCardChangedPiles with the leaving pile
# ═════════════════════════════════════════════════════════════════════════

class TestThieveryDispatchesAfterCardChangedPiles:
    def test_thievery_fires_after_card_changed_piles_with_the_leaving_pile(self):
        cs = fresh_with(ThievingHopper)
        recorder = _PileChangeRecorder()
        cs.hooks.register(recorder)

        cs.end_turn()  # THIEVERY: steal a card

        stolen = cs.enemy.powers["swipe"].stolen_card
        matches = [c for c in recorder.calls if c[0] is stolen]
        assert len(matches) == 1
        _card, pile, cloned_by = matches[0]
        assert pile in ("draw", "discard")   # the pile it left, matching
        assert cloned_by is None             # CardPileCmd.cs:188's `null`

    def test_the_stolen_card_is_unregistered_as_a_hook_listener(self):
        """Unaffected by this task's dispatch fix -- the pile-agnostic
        removal already unregistered the card; kept here as the existing
        behaviour the new dispatch call must not disturb."""
        cs = fresh_with(ThievingHopper)
        cs.end_turn()  # THIEVERY
        stolen = cs.enemy.powers["swipe"].stolen_card
        assert stolen not in cs.hooks._listeners
