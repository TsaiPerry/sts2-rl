"""The enemy side is ONE side turn, not N creature turns (turn_structure G5).

`CombatManager.StartTurn` captures the side's participants once
(CombatManager.cs:444) and then runs three COMPLETE passes over them --
`Creature.BeforeTurnStart` (:449-455), `Creature.AfterTurnStart`/`ClearBlock`
(:492-499) and `Hook.AfterBlockCleared` (:500-507) -- with ONE
`Hook.BeforeSideTurnStart` (:458) between the first and the second and ONE
`Hook.AfterSideTurnStart` (:522) after the third. Only then does
`ExecuteEnemyTurn` (:1072-1090) walk the enemies for their moves, and the side
closes with ONE `Hook.BeforeTurnEnd` (:1251) and ONE `Hook.AfterTurnEnd`
(:1256) in `EndEnemyTurnInternal`.

The sim used to bracket each enemy individually --
[clear, start, move, end] per enemy -- and had no side-scoped enemy turn-start
slot at all, so every side hook an enemy power implements was hand-rolled onto
one of the two per-creature slots. This file pins the fixed shape.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, PowerCmd
from sts2_rl.monsters import Encounter, FuzzyWurmCrawler
from sts2_rl.powers import (
    HardenedShellPower,
    PlatingPower,
    PoisonPower,
    SandpitPower,
    SlowPower,
)

from test_hook_order import trace


SIDE_HOOKS = [
    "before_enemy_side_start",
    "should_clear_block",
    "on_block_cleared",
    "after_enemy_side_start",
    "before_enemy_side_end",
    "on_enemy_side_end",
]


def two_crawlers() -> CombatState:
    return CombatState(
        rng=random.Random(0),
        encounter=Encounter(id="two_crawlers",
                            monster_classes=[FuzzyWurmCrawler,
                                             FuzzyWurmCrawler]),
    )


class TestSidePassStructure:
    def test_three_complete_passes_then_one_side_start(self):
        """[BeforeSideTurnStart, clear1, clear2, cleared1, cleared2,
        AfterSideTurnStart, ...moves..., BeforeTurnEnd, AfterTurnEnd].

        Replaces test_hook_order's `test_enemy_side_is_interleaved_per_enemy`,
        which pinned the old interleaved order as a deliberate trace of the
        gap.
        """
        cs = two_crawlers()
        for e in cs.enemies:
            e.block = 5
        calls = trace(cs.hooks, SIDE_HOOKS)
        cs._run_enemy_turns()
        assert calls == [
            "before_enemy_side_start",      # :458   ONCE
            "should_clear_block",           # :492-499  a complete pass
            "should_clear_block",
            "on_block_cleared",             # :500-507  a complete pass
            "on_block_cleared",
            "after_enemy_side_start",       # :522   ONCE
            # ...the moves (:1072-1090)...
            "before_enemy_side_end",        # :1251  ONCE
            "on_enemy_side_end",            # :1256  ONCE
        ]

    def test_every_enemy_is_unblocked_before_any_of_them_moves(self):
        """The block-clear pass completes for the whole side first, so enemy 2
        cannot still be holding last turn's block while enemy 1 acts."""
        cs = two_crawlers()
        for e in cs.enemies:
            e.block = 5
        seen: list[list[int]] = []

        class Probe:
            def before_attack(self, dealer, card=None):
                seen.append([e.block for e in cs.enemies])

        cs.hooks.register(Probe())
        cs._run_enemy_turns()
        assert seen, "no enemy attacked"
        assert all(blocks == [0, 0] for blocks in seen), seen


class TestSideStartListeners:
    def test_poison_ticks_on_every_enemy_before_any_move(self):
        """PoisonPower.cs:55-73 is `AfterSideTurnStart`, so in a two-enemy
        encounter BOTH enemies have already lost HP by the time the first one
        attacks. On the old per-enemy slot enemy 2 was still at full HP."""
        cs = two_crawlers()
        for e in cs.enemies:
            PowerCmd.apply(cs.hooks, e, PoisonPower, 3, applier=cs.player)
        before = [e.hp for e in cs.enemies]
        seen: list[list[int]] = []

        class Probe:
            def before_attack(self, dealer, card=None):
                seen.append([e.hp for e in cs.enemies])

        cs.hooks.register(Probe())
        cs._run_enemy_turns()
        assert seen, "no enemy attacked"
        assert seen[0] == [before[0] - 3, before[1] - 3]

    def test_sandpit_decrements_in_the_late_pass(self):
        """SandpitPower.cs:70 is `AfterSideTurnStartLate`, so a plain
        `after_enemy_side_start` listener still sees the pre-decrement
        amount."""
        cs = two_crawlers()
        owner = cs.enemies[0]
        PowerCmd.apply(cs.hooks, owner, SandpitPower, 4, applier=owner)
        seen: list[int] = []

        class Probe:
            def after_enemy_side_start(self):
                seen.append(owner.powers["sandpit"].amount)

        cs.hooks.register(Probe())
        cs._run_enemy_turns()
        assert seen == [4]
        assert owner.powers["sandpit"].amount == 3

    def test_slow_resets_once_per_side_not_once_per_enemy(self):
        """SlowPower.cs:52 is `AfterSideTurnStart` with
        `participants.Contains(Owner)`: one reset for the side."""
        cs = two_crawlers()
        owner = cs.enemies[1]
        PowerCmd.apply(cs.hooks, owner, SlowPower, 1, applier=cs.player)
        power = owner.powers["slow"]
        power._cards_this_turn = 4
        cs._run_enemy_turns()
        assert power._cards_this_turn == 0

    def test_hardened_shell_resets_on_both_sides_unfiltered(self):
        """HardenedShellPower.cs:71 is `BeforeSideTurnStart` with NO
        participants filter at all -- it resets on EVERY side's turn start,
        which the old owner-filtered per-enemy slot could not express."""
        cs = two_crawlers()
        owner = cs.enemies[0]
        PowerCmd.apply(cs.hooks, owner, HardenedShellPower, 1, applier=owner)
        power = owner.powers["hardened_shell"]
        power._damage_received_this_turn = 9
        cs._run_enemy_turns()
        assert power._damage_received_this_turn == 0


class TestSideEndListeners:
    def test_plating_gains_block_once_at_the_side_end(self):
        """PlatingPower.cs:61 is `BeforeSideTurnEndEarly` -- one grant for the
        side, at the side end, not one per enemy turn end."""
        cs = two_crawlers()
        owner = cs.enemies[0]
        PowerCmd.apply(cs.hooks, owner, PlatingPower, 4, applier=owner)
        owner.block = 0
        cs._run_enemy_turns()
        assert owner.block == 4

    def test_asleep_drops_plating_before_plating_grants_it(self):
        """AsleepPower.cs:38 is `BeforeSideTurnEndVeryEarly` and
        PlatingPower.cs:61 is `BeforeSideTurnEndEarly`, so on the LAST sleeping
        turn the Plating is gone before it can grant anything. Flattened onto
        one plain pass -- or onto the enemy turn START, where the sim had the
        Asleep half -- the order was luck."""
        from sts2_rl.monsters.underdocks.lagavulin_matriarch import (
            LagavulinMatriarch,
        )

        cs = CombatState(
            rng=random.Random(0),
            encounter=Encounter(id="matriarch_and_crawler",
                                monster_classes=[LagavulinMatriarch,
                                                 FuzzyWurmCrawler]),
        )
        # The Matriarch already starts with both; drop Asleep to its LAST
        # sleeping turn, which is the `Amount <= 1` arm of AsleepPower.cs:38.
        owner = cs.enemies[0]
        assert {"plating", "asleep"} <= set(owner.powers)
        owner.powers["asleep"].amount = 1
        owner.powers["plating"].amount = 4
        owner.block = 0
        cs._run_enemy_turns()
        assert "plating" not in owner.powers
        assert owner.block == 0
