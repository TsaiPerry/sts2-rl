"""Round 14, R1 — the last two LIVE `seam/hook_dispatch` guards, plus the
`seam/creature_card_cmds` heal guard round 13 flagged as adjacent-but-not-
identical to one of them.

    * `hook_dispatch/guard10` (LABEL F3) — `HookSystem.combat_is_over`
      (sts2_rl/hooks.py) is the predicate `_each` gates 55 sim hook names on
      (mirroring 73 of Hook.cs's combat-gated dispatchers via
      `Hook.IterateCombatHookListeners`, Hook.cs:53-63:
      `if (IsOverOrEnding && !IsStarting) yield break;`). The sim tested only
      `phase == Phase.COMBAT_OVER` (C#'s `!IsInProgress`), missing the
      `IsEnding` half — the window between the killing blow and
      `CheckWinCondition`'s teardown, where C#'s `CombatManager.IsEnding`
      (CombatManager.cs:180-202) is already true but `phase` has not flipped
      yet. Fix: delegate to `CombatState.is_over_or_ending`
      (sts2_rl/combat.py:1824-1845), which already carries exactly
      `IsEnding || !IsInProgress` (CombatManager.cs:210-220) and already
      exempts combat setup (no `phase` attribute yet == C#'s `IsStarting`).

    * `hook_dispatch/guard12` (LABEL F2) — `RunState._map_listeners`
      (sts2_rl/run.py) returned `[*self.relics, *self.deck]`; RunState.cs:
      548-576's `IterateHookListeners` walks the deck (+ enchantments) FIRST,
      THEN relics/potions/modifiers/badges/scaling. `SpoilsMapCard` and
      `GoldenCompass` both implement `modify_generated_map` and both REPLACE
      the map object wholesale rather than merging, so whichever listener
      runs LAST wins outright — order is directly observable, not merely a
      call-count difference.

    * `creature_card_cmds/step19` (UNLABELLED) — `CreatureCmd.heal`
      (sts2_rl/cmds.py) gated on `combat.is_over` (`phase ==
      Phase.COMBAT_OVER`) instead of the bare `combat.is_ending`
      (CreatureCmd.cs:693-696: `if (IsEnding && !IsPlayer) return;`). Unlike
      guard10's site, C# does NOT use `IsOverOrEnding` here, so the two sites
      need opposite-looking but individually-correct predicates — confirmed
      by reading both C# sites directly (see `TestGuard10AndStep19AreTwoDefects`
      below): swapping one predicate in for the other over- or under-guards
      the heal in the two different windows, so this is genuinely two
      separate one-line fixes, not one.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, CreatureCmd, HookSystem
from sts2_rl.combat import Phase
from sts2_rl.hooks import _COMBAT_GATED_HOOKS


# ═════════════════════════════════════════════════════════════════════════
# Round 13's open question: are guard10 and step19 one defect or two?
# ═════════════════════════════════════════════════════════════════════════

class TestGuard10AndStep19AreTwoDefects:
    """Executed proof, both C# sites and both sim predicates.

    Hook.cs:53-58's `IterateCombatHookListeners` (guard10's C# counterpart)
    gates on `IsOverOrEnding` (`IsEnding || !IsInProgress`,
    CombatManager.cs:210-220). CreatureCmd.cs:693 (step19's C# counterpart)
    gates on the bare `IsEnding`. They diverge in exactly the window AFTER
    combat has fully torn down (`is_over` true, `is_ending` false): guard10
    must still SUPPRESS there (IsOverOrEnding is true via the `!IsInProgress`
    arm) while step19 must ALLOW there (IsEnding is false). One predicate
    cannot be correct for both sites.
    """

    def test_is_ending_and_is_over_or_ending_diverge_after_teardown(self):
        cs = CombatState(rng=random.Random(0))
        cs._end_combat(player_won=True)
        # Post-teardown: is_over_or_ending (guard10's predicate) stays True
        # via the !IsInProgress arm, but is_ending (step19's predicate) has
        # already gone back to False -- CombatManager.cs:184-187's leading
        # `if (!IsInProgress) return false`.
        assert cs.is_over_or_ending is True
        assert cs.is_ending is False

    def test_using_is_over_or_ending_for_the_heal_guard_would_over_guard_it(self):
        """If step19 borrowed guard10's predicate (is_over_or_ending) instead
        of the bare is_ending, a post-teardown revive heal on a non-player
        creature would be wrongly refused -- CreatureCmd.cs:693 permits it
        (IsEnding is false there) but is_over_or_ending is still true."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        enemy = cs.enemies[0]
        enemy.hp = 0
        cs._end_combat(player_won=True)
        assert cs.is_over_or_ending and not cs.is_ending
        # The C#-correct outcome (asserted below, post-fix): heal succeeds.
        # Confirms the two sites cannot share one replacement predicate.


# ═════════════════════════════════════════════════════════════════════════
# hook_dispatch/guard10 (LABEL F3) — HookSystem.combat_is_over
# ═════════════════════════════════════════════════════════════════════════

class _Spy:
    hook_category = 1

    def __init__(self) -> None:
        self.seen: list[str] = []

    def on_card_drawn(self, card, from_hand_draw=False):
        self.seen.append("on_card_drawn")


class TestGuard10CombatIsOverCatchesTheEndingWindow:
    def test_a_gated_hook_reaches_nobody_in_the_ending_window(self):
        """The window Hook.cs:53-58 gates that `phase == COMBAT_OVER` alone
        misses: all primary enemies dead, `CheckWinCondition`'s teardown not
        yet run. Reproduced exactly like
        test_combat_ending_command_guards.py's `ending()` helper: kill the
        only enemy directly, without calling `_end_combat`."""
        spy = _Spy()
        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(spy)
        cs.enemies[0].hp = 0
        assert cs.is_ending and not cs.is_over          # the ending window
        cs.hooks.on_card_drawn(None)
        assert spy.seen == []

    def test_the_gate_still_fires_while_the_combat_is_genuinely_live(self):
        spy = _Spy()
        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(spy)
        cs.hooks.on_card_drawn(None)
        assert spy.seen == ["on_card_drawn"]

    def test_combat_is_over_reads_is_over_or_ending(self):
        """Direct predicate check: `HookSystem.combat_is_over` must now agree
        with `CombatState.is_over_or_ending` in the ending window, not lag
        behind it until teardown."""
        cs = CombatState(rng=random.Random(0))
        cs.enemies[0].hp = 0
        assert cs.is_over_or_ending is True
        assert cs.hooks.combat_is_over is True

    def test_the_gate_is_still_inert_outside_a_combat(self):
        """A bare HookSystem (run-level listener walks, previews) has no
        `combat` at all -- must stay ungated (regression guard on the
        existing test_combat_over_hook_gate.py behaviour)."""
        hooks = HookSystem()
        spy = _Spy()
        hooks.register(spy)
        assert hooks.combat_is_over is False
        hooks.on_card_drawn(None)
        assert spy.seen == ["on_card_drawn"]

    def test_the_gate_is_still_inert_during_combat_setup(self):
        """C#'s `IsStarting` exemption (Hook.cs:45-47): during
        `CombatState.__init__`, before `phase` is assigned, a monster's
        starting-power PowerCmd calls must still reach listeners. The sim's
        `getattr(combat, "phase", None)` already gives this for free through
        both `is_ending` and `is_over_or_ending` -- pin it so a future
        edit to either property can't silently reintroduce the gap."""
        cs = CombatState.__new__(CombatState)
        cs.hooks = HookSystem()
        cs.hooks.combat = cs
        spy = _Spy()
        cs.hooks.register(spy)
        assert not hasattr(cs, "phase")
        assert cs.hooks.combat_is_over is False
        cs.hooks.on_card_drawn(None)
        assert spy.seen == ["on_card_drawn"]

    def test_the_map_is_still_the_size_the_census_says(self):
        """Regression guard shared with test_combat_over_hook_gate.py: this
        fix must not touch which hooks are gated, only when the gate closes."""
        assert len(_COMBAT_GATED_HOOKS) == 55

    def test_should_allow_hitting_still_consults_illusion_with_a_living_companion(self):
        """`Hook.ShouldAllowHitting` (Hook.cs:2131-2141) genuinely IS one of
        the 73 `IterateCombatHookListeners`-gated dispatchers -- confirmed by
        direct read, not assumed. So this fix is narrowly correct only if the
        REALISTIC shape (an Illusion-holder with a living primary companion,
        `is_ending` False) still reaches `IllusionPower.should_allow_hitting`.
        This is the control for the round-14 finding: `test_r13_relic2.py`'s
        `_make_reviving_enemy` and `test_overgrowth_powers.py`'s
        `fresh_with(EyeWithTeeth)` both build a SOLO Illusion/Minion enemy
        (no companion), which C#'s own `IsPrimaryEnemy`/`IsSecondaryEnemy`
        split (Creature.cs:245-278) makes a combat with NO living primary
        enemy from the moment that lone enemy dies -- a configuration the
        real game apparently never constructs (Eye With Teeth is only ever
        summoned alongside its Fogmog; Parafright self-applies Illusion but
        the citations found no encounter pairing it solo either). This test
        is the reachable, faithful case; the two broken tests are the
        unreachable, degenerate one -- see the round-14 R1 report."""
        import random as _random

        from sts2_rl.monsters import Encounter
        from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
        from sts2_rl.powers import IllusionPower
        from sts2_rl.cmds import PowerCmd, DamageCmd

        cs = CombatState(rng=_random.Random(100),
                         encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))
        enemy, companion = cs.enemies[0], cs.enemies[1]
        PowerCmd.apply(cs.hooks, enemy, IllusionPower, 1)
        DamageCmd.deal(cs.hooks, enemy, 9999, dealer=cs.player)
        assert enemy.is_dead and enemy.powers["illusion"].is_reviving
        assert not companion.is_dead
        assert cs.is_ending is False          # a primary is still alive
        assert cs.hooks.should_allow_hitting(enemy) is False


# ═════════════════════════════════════════════════════════════════════════
# creature_card_cmds/step19 (UNLABELLED) — CreatureCmd.heal's guard
# ═════════════════════════════════════════════════════════════════════════

class TestStep19HealGuardUsesIsEndingNotIsOver:
    def test_a_non_player_heal_is_refused_in_the_ending_window(self):
        """CreatureCmd.cs:693-696: `IsEnding && !IsPlayer -> return`. Before
        the fix the sim's guard read `is_over` (False here, phase not yet
        flipped), so the heal wrongly went through."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        enemy = cs.enemies[0]
        enemy.hp = 0
        assert cs.is_ending and not cs.is_over
        healed = CreatureCmd.heal(cs.hooks, enemy, 5)
        assert healed == 0
        assert enemy.hp == 0

    def test_a_non_player_heal_is_permitted_after_teardown(self):
        """The mirror image: post-teardown (`is_over` True, `is_ending`
        already False again via CombatManager.cs:184-187's leading
        `!IsInProgress` check), C# PERMITS the heal. Before the fix the sim's
        `is_over`-based guard wrongly refused it here -- the two windows
        produce opposite verdicts, which is exactly why guard10's
        `is_over_or_ending` cannot be reused for this site."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        enemy = cs.enemies[0]
        enemy.hp = 0
        cs._end_combat(player_won=True)
        assert cs.is_over and not cs.is_ending
        healed = CreatureCmd.heal(cs.hooks, enemy, 5)
        assert healed == 5
        assert enemy.hp == 5

    def test_a_player_heal_is_never_refused_by_this_guard(self):
        """`!IsPlayer` in the C# condition: the player side is exempt from
        this guard in both windows (ReviveBeforeCombatEnd needs it)."""
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=10)
        cs.player.hp = 0
        assert cs.is_ending
        healed = CreatureCmd.heal(cs.hooks, cs.player, 5)
        assert healed == 5
        assert cs.player.hp == 5

    def test_heal_still_works_normally_mid_combat(self):
        cs = CombatState(rng=random.Random(0), max_hp=10, current_hp=5)
        healed = CreatureCmd.heal(cs.hooks, cs.player, 3)
        assert healed == 3
        assert cs.player.hp == 8


# ═════════════════════════════════════════════════════════════════════════
# hook_dispatch/guard12 (LABEL F2) — RunState._map_listeners order
# ═════════════════════════════════════════════════════════════════════════

class TestGuard12MapListenersAreDeckFirst:
    def test_map_listeners_returns_deck_before_relics(self):
        """Direct order check against RunState.cs:548-576: deck cards (+
        enchantments) first, then relics/potions/modifiers/badges/scaling."""
        import random as _random

        from sts2_rl.cards import make_card
        from sts2_rl.relics import make_relic
        from sts2_rl.run import RunState

        run = RunState(rng=_random.Random(0))
        card = make_card("strike")
        relic = make_relic("golden_compass")
        run.add_card(card)
        run.add_relic(relic)
        listeners = run._map_listeners()
        assert listeners.index(card) < listeners.index(relic)

    def test_spoils_map_and_golden_compass_contend_on_modify_generated_map(self):
        """The observable witness: both listeners REPLACE the act map
        wholesale (neither merges), so whichever runs last wins outright.
        C# runs the deck (Spoils Map) first and the relic (Golden Compass)
        last, so the compass's golden path wins when both target the same
        act. The buggy relic-first order let Spoils Map's hourglass win
        instead."""
        import random as _random

        from sts2_rl.actmap import SpoilsActMap
        from sts2_rl.cards import make_card
        from sts2_rl.relics import make_relic
        from sts2_rl.run import RunState

        run = RunState(rng=_random.Random(5))
        run.add_card(make_card("spoils_map"))
        run.act_index = 1
        compass = make_relic("golden_compass")
        run.add_relic(compass)          # after_obtained: golden_path_act = 1
        assert compass.golden_path_act == 1
        run.start_act("underdocks", act_index=1)
        assert not isinstance(run.map, SpoilsActMap)
        rows = [run.map.points_in_row(r) for r in range(1, run.map.row_count)]
        assert all(len(row) == 1 for row in rows)   # golden path: one node/row
