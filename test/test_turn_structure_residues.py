"""Task 12 -- residue verification for four `seam/turn_structure` mechanisms
carrying "Mostly closed" banners from rounds 4-5:

  A. G11 + step37  -- the enemy-side `Hook.BeforeTurnEnd` slot
     (CombatManager.cs:1250-1256; Hook.cs:1238-1261)
  B. G16 + step63 + step73 -- the `on_hand_emptied` / `AfterFlush` call sites
     (CombatManager.cs:880-893, 1344-1346; Hook.cs:560-570, 611-621)
  C. step14        -- the SECOND, SEPARATE `Hook.AfterBlockCleared` pass and
     its three no-op cases (CombatManager.cs:492-507; Hook.cs:119-125)
  D. G10 + N5       -- the combat-end path's two asymmetric exits
     (CombatManager.cs:945-965, 970-1030, 1046-1059)

`audit/records/seam/turn_structure.json` already carries "CLOSED"/"FIXED"
text for A, B and D (guards G7, G10, G11, G16, N5 and steps 37/63/64/69-73)
-- this file is the EXECUTION that settles whether that text still matches
today's `sts2_rl/combat.py` and `sts2_rl/player.py`, per Task 12's brief.
step14 is still recorded as an open `gap`, and its own "STILL OPEN" prose
(fused clear-and-event loop, old line numbers 359-363/391/393) does not match
the code at combat.py:582-600 any more -- this file is the witness for that
staleness.

Read-only on `sts2_rl/**`; nothing here edits engine or content code. Run:
    py -m pytest test/test_turn_structure_residues.py -v
"""
from __future__ import annotations

import importlib.util
import random

import pytest

from sts2_rl import BarricadePower, CombatState, PowerCmd
from sts2_rl.combat import Phase
from sts2_rl.monsters import Encounter, FuzzyWurmCrawler


def two_crawlers() -> CombatState:
    return CombatState(
        rng=random.Random(0),
        encounter=Encounter(id="two_crawlers_residue",
                            monster_classes=[FuzzyWurmCrawler, FuzzyWurmCrawler]),
    )


# ---------------------------------------------------------------------------
# A. turn_structure/G11 + step37 -- the enemy-side BeforeTurnEnd slot
# ---------------------------------------------------------------------------

class TestA_EnemySideBeforeTurnEndSlot:
    """G11/step37 both carry "CLOSED ... FIXED 2026-07-28 (round 4)" text
    claiming `before_enemy_side_end` reproduces CombatManager.cs:1250-1256's
    three-pass `Hook.BeforeTurnEnd` (VeryEarly, Early, plain -- Hook.cs:
    1238-1261) followed by `PlayerCombatState.EndOfTurnCleanup` for every
    player and then the two-pass `Hook.AfterTurnEnd`. Driven directly against
    today's `_run_enemy_turns` (combat.py:557-659).
    """

    def test_the_three_pass_suffix_walk_runs_in_order(self):
        """Hook.cs:1238-1261 -- BeforeSideTurnEndVeryEarly, then
        BeforeSideTurnEndEarly, then BeforeSideTurnEnd, each a complete pass.
        `HookSystem._each`'s generic suffix walk (hooks.py:283-330) is what
        the sim relies on for this; this test drives it with synthetic
        listeners rather than trusting the docstring."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        seen: list[str] = []

        class Watch:
            def before_enemy_side_end_very_early(self):
                seen.append("very_early")

            def before_enemy_side_end_early(self):
                seen.append("early")

            def before_enemy_side_end(self):
                seen.append("plain")

        cs.hooks.register(Watch())
        cs._run_enemy_turns()
        assert seen == ["very_early", "early", "plain"]

    def test_full_sequence_is_before_turn_end_then_cleanup_then_after_turn_end(self):
        """CombatManager.cs:1250-1256's own order inside
        `EndEnemyTurnInternal`: `Hook.BeforeTurnEnd`, then
        `PlayerCombatState.EndOfTurnCleanup()` for every player (which is
        what clears a single-turn Retain granted from the first hook), then
        `Hook.AfterTurnEnd`."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        card = cs.player.draw_pile[0]
        order: list[str] = []

        class Watch:
            def before_enemy_side_end(self):
                card.give_single_turn_retain()
                order.append(f"before_enemy_side_end:{card.should_retain_this_turn}")

            def on_enemy_side_end(self):
                order.append(f"on_enemy_side_end:{card.should_retain_this_turn}")

        cs.hooks.register(Watch())
        cs._run_enemy_turns()
        assert order == [
            "before_enemy_side_end:True",
            "on_enemy_side_end:False",   # EndOfTurnCleanup ran in between
        ]


# ---------------------------------------------------------------------------
# B. turn_structure/G16 + step63 + step73 -- on_hand_emptied / AfterFlush
# ---------------------------------------------------------------------------

class TestB_OnHandEmptiedAndAfterFlushSites:
    """G16 and step73 carry "CLOSED ... FIXED 2026-07-29 (round 5)" text:
    `_check_for_empty_hand` (combat.py:1239-1260) fires from exactly C#'s two
    real call sites -- after a card play (CardModel.cs:1992) and after a
    potion use (PotionModel.cs:340) -- gated on
    `!IsExecutingCardOrPotionEffect`, and NOT from the end-of-turn flush,
    which CombatManager.cs:880-883 deliberately excludes. step63 is the one
    piece still recorded `"live": false`: `Hook.AfterFlush` (Hook.cs:
    560-570) is a SEPARATE hook the sim has never had a dispatcher for.

    T0's `turn_structure/G7` phantom-key confusion (brief residue B) traces
    to step63's OWN current text, which cites "(guard G7, closed round 5)"
    for the EndOfTurnCleanup half -- `gap_queue.py`'s guard-reference grouping
    files step63 under mechanism key `turn_structure/G7` even though G7 (a
    closed `faithful` guard about `EndOfTurnCleanup`, not `AfterFlush`) is not
    itself a live mechanism. The two tests below drive both halves.
    """

    def test_after_flush_has_no_sim_dispatcher(self):
        """step63's residue: no `after_flush` hook exists on HookSystem, and
        AfterFlush's sole C# implementer (Bookmark.cs:18) has no sim module
        at all -- `sts2_rl.relics.bookmark` does not exist. Confirms the
        DORMANT verdict by execution rather than by a stale grep quoted in
        prose."""
        cs = CombatState(rng=random.Random(0))
        assert not hasattr(cs.hooks, "after_flush")
        assert importlib.util.find_spec("sts2_rl.relics.bookmark") is None

    def test_end_of_turn_cleanup_runs_from_the_flush_and_is_not_after_flush(self):
        """G7 (closed): `discard_hand` (player.py:296-325) calls
        `end_of_turn_cleanup()` as its LAST line -- CombatManager.cs:1346,
        the second of C#'s two per-round EndOfTurnCleanup sites, strictly
        AFTER where `AfterFlush` would sit. This is a plain method call, not
        a hook, and is unrelated to step63's missing `AfterFlush` dispatcher
        -- the two were conflated by G4's old (superseded) close-note text
        and are confirmed separate here."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.hand[0]
        card.add_cost_this_turn(-1)
        base = card._energy_cost
        assert card.energy_cost == max(0, base - 1)
        cs.player.discard_hand()
        assert card.energy_cost == base

    def test_the_flush_site_still_does_not_fire_on_hand_emptied(self):
        """CombatManager.cs:880-883's exclusion, driven with a
        hand-emptying flush. Deliberately duplicates
        `test_turn_structure_gaps.py::TestG16WhereTheHandEmptyCheckRuns::
        test_the_flush_does_not_fire_it` (which also empties the hand — its
        default 5-card hand flushes to []); kept as this file's own explicit
        pin of residue B. [Docstring corrected 2026-07-30 after task review:
        the original claimed the older test "does not empty the hand", which
        is false.]"""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.player.hand.clear()
        cs.player.hand.append(cs.player.draw_pile.pop())
        seen = []

        class Watch:
            def on_hand_emptied(self, player):
                seen.append(player)

        cs.hooks.register(Watch())
        cs.player.discard_hand()
        assert cs.player.hand == []
        assert seen == []


# ---------------------------------------------------------------------------
# C. turn_structure/step14 -- the SECOND, SEPARATE AfterBlockCleared pass
# ---------------------------------------------------------------------------

class TestC_AfterBlockClearedSecondPassReachesAllThreeNoOpCases:
    """step14 is still recorded `"verdict": "gap"` with prose saying the sim
    fuses the clear and the event into ONE per-enemy loop (citing old line
    numbers combat.py:359-363/391/393). Today's `_run_enemy_turns`
    (combat.py:582-600) runs the clear (a complete pass) and the event
    (a second, complete pass) BEFORE any enemy moves -- the shape guards G1
    and G5 already closed. This class re-drives the three no-op cases the
    step's own `what` text names, against today's code, on BOTH sides.
    """

    def test_a_creature_with_no_block_still_gets_the_event(self):
        cs = two_crawlers()
        for e in cs.enemies:
            e.block = 0
        cs.player.hp = 999
        seen = []

        class Watch:
            def on_block_cleared(self, creature):
                seen.append(creature)

        cs.hooks.register(Watch())
        cs._run_enemy_turns()
        assert seen == list(cs.enemies)

    def test_a_prevented_clear_still_gets_the_event(self):
        """BarricadePower.should_clear_block (powers.py:240-243) vetoes the
        clear for its OWNER only; the second pass must still reach that
        owner even though `enemy.block` was never touched."""
        cs = two_crawlers()
        owner, other = cs.enemies
        PowerCmd.apply(cs.hooks, owner, BarricadePower, 1, applier=owner)
        owner.block = 7
        other.block = 0
        cs.player.hp = 999
        seen = []

        class Watch:
            def on_block_cleared(self, creature):
                seen.append(creature)

        cs.hooks.register(Watch())
        cs._run_enemy_turns()
        assert owner.block == 7           # the clear really was prevented...
        assert other.block == 0           # ...the other enemy cleared normally...
        assert seen == [owner, other]     # ...but BOTH still got the event

    def test_a_turn_one_player_whose_clear_never_ran_still_gets_the_event(self):
        """Creature.AfterTurnStart (Creature.cs:681-692) returns BEFORE
        ClearBlock for `TurnNumber == 1`; player.py:213-226 mirrors that with
        `if not self._first_turn:` around the clear ALONE, with
        `on_block_cleared` outside and after it -- unconditional."""
        cs = CombatState(rng=random.Random(0))
        cs.player._first_turn = True      # re-arm the turn-1 branch
        cs.player.block = 9
        seen = []

        class Watch:
            def on_block_cleared(self, creature):
                seen.append(creature)

        cs.hooks.register(Watch())
        cs.player.start_turn()
        assert cs.player.block == 9       # AfterTurnStart returned early...
        assert seen == [cs.player]        # ...but the second pass still ran

    def test_the_pass_is_complete_before_the_first_event_fires(self):
        """Falsifies the record's still-open text directly: if the clear and
        the event were still fused per-enemy (the old combat.py:359-363
        shape), the FIRST `on_block_cleared` would see one enemy still
        holding last turn's block. Today it does not -- both are already 0,
        proving the clear pass runs to completion before the event pass
        starts (CombatManager.cs:492-507's two complete loops)."""
        cs = two_crawlers()
        for e in cs.enemies:
            e.block = 5
        cs.player.hp = 999
        first_event_snapshot: list[list[int]] = []

        class Watch:
            def on_block_cleared(self, creature):
                if not first_event_snapshot:
                    first_event_snapshot.append([e.block for e in cs.enemies])

        cs.hooks.register(Watch())
        cs._run_enemy_turns()
        assert first_event_snapshot == [[0, 0]]


# ---------------------------------------------------------------------------
# D. turn_structure/G10 + N5 -- the combat-end path
# ---------------------------------------------------------------------------

class TestD_CombatEndPathSiteEntries:
    """G10 carries "CLOSED ... FIXED 2026-07-29 (round 5)" text: `lose_combat`
    only MARKS (CombatManager.cs:945-951); `_check_win_condition` tests the
    pending loss FIRST (:1048) and routes to `_process_pending_loss` (no
    hook, :956-965) or `_end_combat_internal` (revive then AfterCombatEnd
    then AfterCombatVictory, :970-1030). `test_turn_structure_gaps.py`'s
    `TestG10TheCombatEndPath` already pins that shape by calling
    `_check_win_condition`/`_end_combat` directly; this class instead drives
    the ACTUAL per-move exit inside `_run_enemy_turns`
    (combat.py:639-645) -- the site `ExecuteEnemyTurn`'s own
    `await CheckWinCondition()` (CombatManager.cs:1082) occupies -- through a
    real lethal attack, and confirms `should_stop_combat_from_ending`
    (Task 26's mechanism) is still reachable from G10's own win predicate.
    """

    class _Watch:
        def __init__(self):
            self.seen: list[str] = []

        def on_combat_end(self):
            self.seen.append("end")

        def on_combat_victory_early(self):
            self.seen.append("victory_early")

        def on_combat_victory(self):
            self.seen.append("victory")

    def test_a_lethal_enemy_move_mid_turn_takes_the_no_hook_loss_exit(self):
        """FuzzyWurmCrawler's opening move, FIRST_ACID_GOOP, is a 4-damage
        attack (monsters/fuzzy_wurm_crawler.py:19). At 1 HP the player dies
        INSIDE `enemy.take_turn(...)`, so this exercises the per-move
        `if self.player.is_dead:` exit (combat.py:639-642), not the
        top-level helpers the existing G10 tests call directly."""
        cs = CombatState(
            rng=random.Random(0),
            encounter=Encounter(id="lethal_crawler_residue",
                                monster_classes=[FuzzyWurmCrawler]),
        )
        cs.player.hp = 1
        w = self._Watch()
        cs.hooks.register(w)
        cs._run_enemy_turns()
        assert cs.phase is Phase.COMBAT_OVER
        assert cs.result is not None and not cs.result.player_won
        assert w.seen == []          # ProcessPendingLoss's shape: no hook at all

    def test_should_stop_combat_from_ending_still_gates_all_enemies_dead(self):
        """`_all_enemies_dead` (combat.py:433-443) is G10/N5's own win
        predicate and its last gate is `should_stop_combat_from_ending()` --
        CombatManager.cs:196's position. NOT this task's mechanism to close
        (Task 26 owns the hook surface); this only confirms G10's predicate
        still reaches it, so a future edit to G10 cannot silently detach it."""
        cs = CombatState(rng=random.Random(0))
        for e in cs.enemies:
            e.hp = 0

        class HoldOpen:
            def should_stop_combat_from_ending(self):
                return True

        cs.hooks.register(HoldOpen())
        assert not cs._all_enemies_dead()
        assert not cs.is_ending
