"""Tier-2 Task 11: five small missing/misordered dispatchers, one
false-premise removal, and one false-premise NON-fix (audit/GAP-QUEUE.md
mechanisms creature_card_cmds/step12, creature_card_cmds/step46,
turn_structure/step20, turn_structure/step55, turn_structure/step17,
hook_dispatch/step37; item G has no gap record -- see combat.py's
`_process_turn_end_cards`).

Item F (hook_dispatch/step37) turned out to be premise-false on review
(2026-07-31): the sim's `any(...)` was already faithful to C#'s genuinely
short-circuiting `||`. Its class here pins the CORRECT (short-circuiting)
behavior as a regression guard, not a fix.

One test class per item, each pinning the exact C# citation the task-11
brief and gap records name.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import BlockCmd
from sts2_rl.relics import Relic, RelicRarity
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.valueprops import ValueProp


def fresh(seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), **kwargs)


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ═════════════════════════════════════════════════════════════════════════
# Item A -- creature_card_cmds/step12: BeforeBlockGained
# ═════════════════════════════════════════════════════════════════════════

class TestBeforeBlockGained:
    def test_fires_with_the_raw_pre_modifier_amount(self):
        """CreatureCmd.cs:642 fires Hook.BeforeBlockGained BEFORE ModifyBlock's
        additive/multiplicative chain (:644), carrying the unmodified amount --
        so a listener sees the raw amount even when another listener doubles
        the final gain."""
        seen = []

        class _Doubler:
            def modify_block_multiplicative(self, target, amount, card=None,
                                             props=ValueProp.NONE):
                return 2.0

        class _Spy:
            def before_block_gained(self, target, amount, card=None,
                                     props=ValueProp.NONE):
                seen.append(amount)

        cs = fresh()
        cs.hooks.register(_Doubler())
        cs.hooks.register(_Spy())
        gained = BlockCmd.apply(cs.hooks, cs.player, 5, card=make_card("defend"))
        assert gained == 10          # doubled by the modifier chain
        assert seen == [5]           # BeforeBlockGained saw the RAW 5

    def test_fires_before_modify_block_additive(self):
        cs = fresh()
        order = []

        class _Spy:
            def before_block_gained(self, target, amount, card=None,
                                     props=ValueProp.NONE):
                order.append("before_block_gained")

            def modify_block_additive(self, target, amount, card=None,
                                      props=ValueProp.NONE):
                order.append("modify_block_additive")
                return 0

        cs.hooks.register(_Spy())
        BlockCmd.apply(cs.hooks, cs.player, 5, card=make_card("defend"))
        assert order == ["before_block_gained", "modify_block_additive"]


# ═════════════════════════════════════════════════════════════════════════
# Item B -- creature_card_cmds/step46: BeforeCardAutoPlayed
# ═════════════════════════════════════════════════════════════════════════

class TestBeforeCardAutoPlayed:
    def test_fires_between_energy_spent_and_before_card_played(self):
        """CardCmd.cs:122 fires Hook.BeforeCardAutoPlayed right before
        card.OnPlayWrapper (:130), which is where BeforeCardPlayed eventually
        fires (CardModel.cs:1929). The sim's auto-play path already fires
        on_energy_spent(card, 0) first (combat.py); this pins the new
        dispatcher landing strictly between the two."""
        order = []

        class _Spy:
            def on_energy_spent(self, card, amount):
                order.append("on_energy_spent")

            def before_card_auto_played(self, card, target=None,
                                        auto_play_type="default"):
                # `auto_play_type` is C#'s AutoPlayType (CardCmd.cs:122),
                # carried by the dispatcher as of round 13 R5 so the Sly tail
                # can pass SlyDiscard (:203).
                order.append(f"before_card_auto_played:{auto_play_type}")

            def before_card_played(self, card, target=None):
                order.append("before_card_played")

        cs = fresh()
        cs.hooks.register(_Spy())
        card = make_card("defend")
        cs.player.hand.append(card)
        cs.auto_play_card(card)
        assert order == [
            "on_energy_spent", "before_card_auto_played:default",
            "before_card_played",
        ]


# ═════════════════════════════════════════════════════════════════════════
# Item C -- turn_structure/step20: AfterModifyingHandDraw
# ═════════════════════════════════════════════════════════════════════════

class TestAfterModifyingHandDraw:
    def test_fires_only_for_listeners_that_actually_changed_the_count(self):
        """CombatManager.cs:654-655: `handDraw = Hook.ModifyHandDraw(..., out
        modifiers); await Hook.AfterModifyingHandDraw(state, modifiers);` --
        `modifiers` is the C# `out` list of listeners whose delta was
        nonzero, mirrored here: a listener that left the count unchanged must
        not be notified."""
        fired = []

        class _Adds:
            def modify_hand_draw(self, player, count):
                return count + 1

            def after_modifying_hand_draw(self):
                fired.append("adds")

        class _NoOp:
            def modify_hand_draw(self, player, count):
                return count

            def after_modifying_hand_draw(self):
                fired.append("noop")

        cs = fresh()
        cs.hooks.register(_Adds())
        cs.hooks.register(_NoOp())
        cs.player.hand.clear()
        cs.player.draw_pile.clear()
        cs.player.draw_pile.extend([make_card("strike") for _ in range(20)])
        cs.player.start_turn()
        assert fired == ["adds"]
        assert len(cs.player.hand) == 6  # base 5 + _Adds' +1

    def test_fires_after_modify_hand_draw_and_before_the_draw(self):
        """Only a listener that actually changed the count is notified (see
        the test above), so this listener must modify the count to observe
        after_modifying_hand_draw's position at all."""
        order = []

        class _Spy:
            def modify_hand_draw(self, player, count):
                order.append("modify_hand_draw")
                return count + 1

            def after_modifying_hand_draw(self):
                order.append("after_modifying_hand_draw")

            def on_card_drawn(self, card, from_hand_draw=False):
                order.append("on_card_drawn")

        cs = fresh()
        cs.hooks.register(_Spy())
        cs.player.hand.clear()
        cs.player.draw_pile.clear()
        cs.player.draw_pile.extend([make_card("strike") for _ in range(20)])
        cs.player.start_turn()
        assert order == [
            "modify_hand_draw", "after_modifying_hand_draw",
            "on_card_drawn", "on_card_drawn", "on_card_drawn",
            "on_card_drawn", "on_card_drawn", "on_card_drawn",
        ]

    def test_a_both_phases_listener_fires_its_after_hook_exactly_once(self):
        """Reviewed 2026-07-31: modify_hand_draw's _each() runs a phased
        listener's plain AND _late implementation in the SAME dispatch
        (Hook.cs's two ModifyHandDraw/ModifyHandDrawLate loops build into
        one out-list), so a listener that changes the count in BOTH phases
        is appended to `modifiers` TWICE. C#'s AfterModifyingHandDraw
        (Hook.cs:739-749) walks the full listener order and calls each one
        `if (modifiers.Contains(modifier))` -- at most once per listener,
        regardless of how many times it is in `modifiers`. Iterating
        `modifiers` directly (the sim's first pass at this) double-fires."""
        fired = []

        class _BothPhases:
            def modify_hand_draw(self, player, count):
                return count + 1

            def modify_hand_draw_late(self, player, count):
                return count + 1

            def after_modifying_hand_draw(self):
                fired.append("both_phases")

        cs = fresh()
        spy = _BothPhases()
        cs.hooks.register(spy)
        modifiers: list = []
        result = cs.hooks.modify_hand_draw(
            cs.player, cs.player.DRAW_PER_TURN, modifiers)
        assert result == cs.player.DRAW_PER_TURN + 2  # both phases applied
        assert modifiers.count(spy) == 2               # recorded from BOTH passes
        cs.hooks.after_modifying_hand_draw(modifiers)
        assert fired == ["both_phases"]                 # but notified only once


# ═════════════════════════════════════════════════════════════════════════
# Item D -- turn_structure/step55: BeforeFlush
# ═════════════════════════════════════════════════════════════════════════

class TestBeforeFlush:
    def test_fires_after_turn_end_cards_and_before_should_flush(self):
        """CombatManager.cs:1200-1206: Hook.BeforeFlush fires per player,
        after the DoTurnEnd loop (turn-end-in-hand cards) and before the
        CheckWinCondition that closes EndPlayerTurnPhaseOneInternal -- so
        strictly before FlushPlayerHand's own Hook.ShouldFlush (:1327)."""
        order = []

        class _Spy:
            def before_flush(self, player):
                order.append("before_flush")

            def should_flush_hand(self):
                order.append("should_flush_hand")
                return True

        cs = fresh()
        cs.hooks.register(_Spy())
        cs.end_turn()
        assert order == ["before_flush", "should_flush_hand"]


# ═════════════════════════════════════════════════════════════════════════
# Item E -- turn_structure/step17: energy-hook order swap
# ═════════════════════════════════════════════════════════════════════════

class TestEnergyHookOrder:
    def test_should_reset_energy_fires_before_modify_max_energy(self):
        """CombatManager.cs:641-649: `if (Hook.ShouldPlayerResetEnergy(...))`
        is evaluated FIRST; `MaxEnergy` (== Hook.ModifyMaxEnergy(...)) is only
        read inside the chosen branch. The sim used to call modify_max_energy
        first."""
        order = []

        class _Spy:
            def should_reset_energy(self, player):
                order.append("should_reset_energy")
                return True

            def modify_max_energy(self, player, amount):
                order.append("modify_max_energy")
                return amount

        cs = fresh()
        cs.hooks.register(_Spy())
        cs.player.start_turn()
        assert order == ["should_reset_energy", "modify_max_energy"]

    def test_arithmetic_is_unchanged_by_the_reorder(self):
        """The swap only changes hook-firing order; ShouldPlayerResetEnergy
        True still means Energy = MaxEnergy exactly as before."""
        cs = fresh()
        cs.player.energy = 1
        cs.player.start_turn()
        assert cs.player.energy == cs.player.ENERGY_PER_TURN


# ═════════════════════════════════════════════════════════════════════════
# Item F -- hook_dispatch/step37: PREMISE FALSE, no fix (reviewed
# 2026-07-31). The record's claim that C#'s `flag = flag ||
# item.ShouldX(...)` (Hook.cs:2472-2493) visits every listener even after
# one returns True is WRONG: C#'s `||` is genuine short-circuit IL,
# confirmed three ways -- the language spec, a compiled-and-run
# reproduction of the exact pattern (only the first listener fired), and
# same-file corroboration at Hook.cs:1451-1452, where the developers
# explicitly hoisted a listener call onto its own line (`bool flag2 =
# item.TryModify...; flag = flag || flag2;`) precisely to AVOID this skip
# -- proof the decompiled `||` is not a mis-rendered bitwise `|=`. The
# sim's `any(...)` (rewards.py's should_force_potion_reward, run.py's
# should_allow_free_travel) was ALREADY faithful; a same-task attempt to
# "fix" it to a full-visit loop was reverted. This class pins the CORRECT
# (short-circuiting) behavior as a regression guard against that reverted
# change recurring.
# ═════════════════════════════════════════════════════════════════════════

class _AlwaysTrue(Relic):
    id = "_t11_always_true"
    name = "Always True"
    rarity = RelicRarity.COMMON

    def should_force_potion_reward(self, run, room_type) -> bool:
        self.calls.append("first")
        return True

    def should_allow_free_travel(self) -> bool:
        self.calls.append("first")
        return True


class _SpyRelic(Relic):
    id = "_t11_spy"
    name = "Spy"
    rarity = RelicRarity.COMMON

    def should_force_potion_reward(self, run, room_type) -> bool:
        self.calls.append("second")
        return False

    def should_allow_free_travel(self) -> bool:
        self.calls.append("second")
        return False


class TestPredicateShortCircuitsFaithfully:
    def test_should_force_potion_reward_short_circuits_like_the_game(self):
        calls: list[str] = []
        first, second = _AlwaysTrue(), _SpyRelic()
        first.calls = second.calls = calls
        run = fresh_run()
        run.relics.extend([first, second])
        run.generate_combat_rewards(RoomType.MONSTER)
        assert calls == ["first"]  # the second relic's predicate is skipped

    def test_should_allow_free_travel_short_circuits_like_the_game(self):
        calls: list[str] = []
        first, second = _AlwaysTrue(), _SpyRelic()
        first.calls = second.calls = calls
        run = fresh_run()
        run.start_act("overgrowth")
        run.relics.extend([first, second])
        run.travelable_points()
        assert calls == ["first"]  # the second relic's predicate is skipped


# ═════════════════════════════════════════════════════════════════════════
# Item G -- false-premise removal: no AfterCardDiscarded from the
# turn-end-in-hand path (combat.py's _process_turn_end_cards)
# ═════════════════════════════════════════════════════════════════════════

class TestTurnEndInHandDiscardFiresNoAfterCardDiscarded:
    def test_burn_discarded_at_turn_end_does_not_fire_on_card_discarded(self):
        """CardModel.cs:1682-1698 (OnTurnEndInHandWrapper): the non-Ethereal
        branch calls `CardPileCmd.Add(this, PileType.Discard...)` directly --
        no Hook.AfterCardDiscarded. Its sole C# call site is CardCmd.cs:194,
        inside DiscardAndDraw (Concentrate/Sly/Gambler's Brew/Gambling Chip),
        which this path is not. Named-work filing 2026-07-30 (no gap id);
        same class as tier-2 Task 10's G11 premise reversal."""
        fired = []

        class _Spy:
            def on_card_discarded(self, card):
                fired.append(card)

        cs = fresh()
        cs.hooks.register(_Spy())
        p = cs.player
        p.hand.clear()
        p.hand.append(make_card("burn"))
        p.block = 99  # absorb Burn so nobody dies
        # Exercise _process_turn_end_cards directly (not the full end_turn()
        # cycle): end_turn() also runs the enemy side and the NEXT player
        # turn's hand draw synchronously, which can reshuffle discard back
        # into the draw pile and redraw Burn -- unrelated to what item G
        # changes and just noise for this assertion.
        cs._process_turn_end_cards()
        assert fired == []
        assert any(c.id == "burn" for c in p.discard_pile)
