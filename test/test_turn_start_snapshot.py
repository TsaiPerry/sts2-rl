"""Task 13 -- `turn_structure/step8` (AmountOnTurnStart snapshot) +
`turn_structure/step32`+`step67` (SpawnedThisTurn / OnSideSwitch).

Mechanism A (step8): `Creature.BeforeTurnStart` (Creature.cs:673-679) snapshots
every power's `Amount` into `AmountOnTurnStart` before ANYTHING else in the
turn (CombatManager.cs:449-455). Two ported readers consult it:
`DrawCardsNextTurnPower` (DrawCardsNextTurnPower.cs:19-38) and
`HelloWorldPower` (HelloWorldPower.cs:19-27) -- a stack applied during the
turn's own setup window (after the snapshot already ran, so it reads the
type's zero default) neither acts nor expires that turn, only the next.

Mechanism B (step32/step67): `CombatManager.AddCreature` ->
`MonsterModel.SetUpForCombat` (MonsterModel.cs:409-413) sets `SpawnedThisTurn
= true` for EVERY creature addition -- the initial roster AND every
mid-combat spawn alike, since C# routes both through the same call
(SetUpCombat's loop / CreatureCmd.Add). `SwitchSides` -> `OnSideSwitch`
(CombatManager.cs:1420-1424; MonsterModel.cs:479-483) clears it once per side
switch. `Creature.TakeTurn`'s guard (Creature.cs:706-716) is the ONLY C#
reader (confirmed by `grep -rn SpawnedThisTurn` over the decompiled source --
exactly 4 hits: the field, its two setters, this one getter), fired only from
`ExecuteEnemyTurn`'s move loop (CombatManager.cs:1072-1090). That loop takes
its OWN fresh `_state.Enemies.ToList()` snapshot AFTER
`Hook.AfterSideTurnStart` has already run (CombatManager.cs's StartTurn body)
-- so a creature that joins the fight DURING that hook (Poison killing an
InfestedPower/StockPower/SurprisePower owner, whose AfterDeath spawns a
replacement) IS in this pass's move loop, with SpawnedThisTurn still True,
and C# skips its PerformMove for that one turn. The audit record's DORMANT
verdict ("no reachable C# path was found") missed this window -- this file's
`TestSpawnedThisTurnPokerSideStartSpawn` class is the reachability witness.

The no-IsDead-guard half (a retained corpse keeps taking its turn, which is
how a withered Decimillipede segment reaches REATTACH) is untouched by this
task; `TestRetainedCorpseSurvivesUnchanged` re-pins it here in addition to
the full `test_hive.py::TestDecimillipede` suite.

Read-only elsewhere: this file exercises `sts2_rl/combat.py`,
`sts2_rl/creatures.py`, `sts2_rl/monsters/base.py` (the `spawned_this_turn`
flag only) and `sts2_rl/powers.py`'s `DrawCardsNextTurnPower` /
`HelloWorldPower` classes -- the only files this task's parallel-work
contract permits editing. Run:
    py -m pytest test/test_turn_start_snapshot.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, CreatureCmd, DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter, Intent, Monster, MoveType
from sts2_rl.monsters.glory.axebot import Axebot
from sts2_rl.monsters.hive import DECIMILLIPEDE_ELITE
from sts2_rl.player import PlayerCombatState
from sts2_rl.powers import DrawCardsNextTurnPower, HelloWorldPower, PoisonPower


def fresh() -> CombatState:
    return CombatState(rng=random.Random(0))


# ---------------------------------------------------------------------------
# Mechanism A -- turn_structure/step8: the AmountOnTurnStart snapshot
# ---------------------------------------------------------------------------

class TestAmountOnTurnStartSnapshotOrdering:
    """The snapshot itself (`Creature.snapshot_powers_on_turn_start`), tested
    independently of either ported reader, mirroring Creature.cs:673-679's
    "before anything else in the turn" placement."""

    def test_snapshot_runs_before_before_side_turn_start_for_every_power(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DrawCardsNextTurnPower, 5)
        seen = []

        class Watch:
            def before_side_turn_start(self, player):
                seen.append(getattr(
                    player.powers["draw_cards_next_turn"],
                    "amount_on_turn_start", "MISSING",
                ))

        cs.hooks.register(Watch())
        cs.end_turn()
        assert seen == [5]

    def test_a_power_applied_after_the_snapshot_was_never_snapshotted(self):
        """A power that did not exist yet at BeforeTurnStart genuinely has no
        `amount_on_turn_start` attribute at all -- it is the READERS'
        `getattr(self, "amount_on_turn_start", 0)` that supplies the 0
        default a fresh C# field would read, not a value this snapshot ever
        wrote for it."""
        cs = fresh()

        class ApplyThenObserve:
            def __init__(self):
                self.was_snapshotted = None

            def on_player_turn_start(self, player):
                PowerCmd.apply(cs.hooks, player, DrawCardsNextTurnPower, 1)
                self.was_snapshotted = hasattr(
                    player.powers["draw_cards_next_turn"], "amount_on_turn_start")

        watch = ApplyThenObserve()
        cs.hooks.register(watch)
        cs.end_turn()
        assert watch.was_snapshotted is False


class TestDrawCardsNextTurnGuard:
    """DrawCardsNextTurnPower.cs:19-38 -- ModifyHandDraw and the
    AfterSideTurnStart removal share ONE `AmountOnTurnStart == 0` guard."""

    def test_applied_during_the_turn_start_window_neither_draws_nor_expires(self):
        cs = fresh()

        class ApplyOnceAtWindowOpen:
            def __init__(self):
                self.fired = False

            def before_side_turn_start(self, player):
                if not self.fired:
                    self.fired = True
                    PowerCmd.apply(cs.hooks, player, DrawCardsNextTurnPower, 3)

        cs.hooks.register(ApplyOnceAtWindowOpen())

        cs.end_turn()  # -> turn 2: applied AFTER turn 2's own snapshot
        assert cs.player.powers["draw_cards_next_turn"].amount == 3
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN

        cs.end_turn()  # -> turn 3: NOW it existed at the snapshot
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN + 3
        assert "draw_cards_next_turn" not in cs.player.powers

    def test_normally_applied_stack_still_draws_and_expires_next_turn(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, DrawCardsNextTurnPower, 2)
        cs.end_turn()
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN + 2
        assert "draw_cards_next_turn" not in cs.player.powers


class TestHelloWorldGuard:
    """HelloWorldPower.cs:19-27 -- BOTH the `>= 1` eligibility guard and the
    generated card COUNT read `AmountOnTurnStart`, not `Amount`."""

    def test_applied_during_the_turn_start_window_grants_nothing_this_turn(self):
        cs = fresh()

        class ApplyOnceAtWindowOpen:
            def __init__(self):
                self.fired = False

            def before_side_turn_start(self, player):
                if not self.fired:
                    self.fired = True
                    PowerCmd.apply(cs.hooks, player, HelloWorldPower, 2)

        cs.hooks.register(ApplyOnceAtWindowOpen())

        cs.end_turn()  # -> turn 2: applied AFTER turn 2's own snapshot
        assert cs.player.powers["hello_world"].amount == 2
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN

        cs.end_turn()  # -> turn 3: NOW it existed at the snapshot
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN + 2

    def test_normally_present_stack_grants_the_snapshotted_amount(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.player, HelloWorldPower, 2)
        cs.end_turn()
        assert len(cs.player.hand) == PlayerCombatState.DRAW_PER_TURN + 2


# ---------------------------------------------------------------------------
# Mechanism B -- turn_structure/step32+step67: SpawnedThisTurn / OnSideSwitch
# ---------------------------------------------------------------------------

class _CountingMonster(Monster):
    """A minimal hand-rolled monster whose `take_turn` just counts calls --
    isolates the SpawnedThisTurn mechanism from any particular ported
    power's own quirks (Wriggler's start-stunned spawn muddies the stun
    branch; this does not)."""

    min_hp = 10
    max_hp = 10

    def __init__(self, hooks, rng=None):
        super().__init__(hooks, rng or random.Random(0))
        self.moves_taken = 0

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.DEFEND)

    def take_turn(self, ctx) -> None:
        self.moves_taken += 1


class TestSpawnedThisTurnAtCombatSetup:
    def test_the_initial_roster_still_acts_on_its_first_enemy_turn(self):
        """SetUpCombat's own AddCreature loop sets SpawnedThisTurn=true for
        every starting monster too (MonsterModel.cs:409-413) -- the FIRST
        SwitchSides (ending turn 1) clears it before ExecuteEnemyTurn ever
        reads it, so the whole roster acts normally from turn 1 on."""
        cs = CombatState(rng=random.Random(0), encounter=Encounter(
            id="counting_sentinel_initial", monster_classes=[_CountingMonster]))
        sentinel = cs.enemy
        assert sentinel.spawned_this_turn  # true from construction...
        cs.end_turn()
        assert sentinel.moves_taken == 1   # ...but cleared before it mattered


class TestSpawnedThisTurnSideStartSpawn:
    """The reachability witness: a creature added during
    Hook.AfterSideTurnStart (`after_enemy_side_start`) -- BEFORE
    ExecuteEnemyTurn's own move-loop snapshot -- carries SpawnedThisTurn=True
    into that same pass's TakeTurn guard."""

    def test_monster_spawned_during_after_enemy_side_start_skips_this_turn_then_acts_next_turn(self):
        cs = CombatState(rng=random.Random(0), encounter=Encounter(
            id="counting_sentinel_spawn", monster_classes=[_CountingMonster]))
        cs.player.hp = 999
        spawn = _CountingMonster(cs.hooks, random.Random(0))

        class SpawnOnceAtSideStart:
            def __init__(self):
                self.fired = False

            def after_enemy_side_start(self):
                if not self.fired:
                    self.fired = True
                    CreatureCmd.add(cs.hooks, spawn)

        cs.hooks.register(SpawnOnceAtSideStart())

        cs._run_enemy_turns()  # turn 1's enemy phase
        assert spawn in cs.enemies
        assert spawn.moves_taken == 0            # PerformMove never ran...
        assert not spawn.performed_first_move    # ...so OnMovePerformed didn't either

        cs._run_enemy_turns()  # turn 2's enemy phase
        assert spawn.moves_taken == 1            # acts normally from here on
        assert spawn.performed_first_move

    def test_axebot_respawn_from_a_poison_kill_during_side_start_skips_boot_up_this_turn(self):
        """Real content, not a synthetic probe: StockPower.AfterDeath
        (powers.py's StockPower.on_death) spawns the respawn Axebot, and
        Poison resolves in `after_enemy_side_start` -- so poisoning the
        Axebot to death on exactly its own turn's tick reproduces the live
        C# path with no synthetic listener at all. The respawn's opening
        move is BOOT_UP (10 block); the fix means it does not fire the SAME
        enemy turn it spawns."""
        cs = CombatState(rng=random.Random(0), encounter=Encounter(
            id="single_axebot_poison", monster_classes=[Axebot]))
        cs.player.hp = 999
        original = cs.enemy
        original.hp = 1
        PowerCmd.apply(cs.hooks, original, PoisonPower, 1)

        cs.end_turn()  # turn 1's enemy phase: Poison kills the original
        assert original.is_gone
        respawns = [e for e in cs.enemies if e is not original]
        assert len(respawns) == 1
        respawn = respawns[0]
        assert respawn.powers["stock"].amount == 1
        assert respawn.block == 0             # BOOT_UP did not fire this turn
        assert not respawn.performed_first_move

        cs.end_turn()  # turn 2's enemy phase: acts normally
        assert respawn.block == 10            # BOOT_UP fired this time


class TestSpawnedThisTurnPlayerSideSpawnIsUnaffected:
    def test_monster_spawned_during_the_players_own_turn_is_not_skipped_next_enemy_turn(self):
        """A creature added while `current_side == "player"` (the ordinary
        case -- SurprisePower/InfestedPower/StockPower firing off a player's
        own attack) is cleared by the very next SwitchSides, well before the
        enemy phase that follows ever reads the flag; this is the ALREADY
        reachable, ALREADY correct case this task's C# reading confirmed --
        pinned here so a future change to the clear site cannot regress it."""
        cs = CombatState(rng=random.Random(0), encounter=Encounter(
            id="counting_sentinel_player_side", monster_classes=[_CountingMonster]))
        spawn = _CountingMonster(cs.hooks, random.Random(0))
        assert cs.current_side == "player"
        CreatureCmd.add(cs.hooks, spawn)   # mirrors a player-turn spawn
        assert spawn.spawned_this_turn

        cs.end_turn()   # first enemy phase this creature ever sees
        assert spawn.moves_taken == 1


class TestRetainedCorpseSurvivesUnchanged:
    """The brief's explicit survival requirement: the no-IsDead-guard half
    (a withered Decimillipede segment keeps taking turns) must be untouched.
    Duplicates (deliberately) `test_hive.py::TestDecimillipede`'s coverage as
    this task's own pin, in addition to running that suite unmodified."""

    def test_a_withered_segment_still_takes_its_turn_every_enemy_phase(self):
        cs = CombatState(rng=random.Random(0), encounter=DECIMILLIPEDE_ELITE)
        victim = cs.enemies[0]
        # Still turn 1's PLAYER phase -- no `_run_enemy_turns` has run yet,
        # so the segment still carries construction's SpawnedThisTurn=True,
        # same as every other initial-roster monster at this point.
        assert victim.spawned_this_turn
        DamageCmd.deal(cs.hooks, victim, 999, dealer=cs.player)
        assert victim.hp == 0
        assert victim.retained_after_death
        assert victim in cs.enemies
        cs.player.hp = 80
        cs.end_turn()   # DEAD_MOVE, then telegraphs REATTACH -- first
                         # `_run_enemy_turns` clears the flag, same as any
                         # other initial-roster monster, and the corpse
                         # still takes this turn regardless (no IsDead guard)
        assert not victim.spawned_this_turn
        assert victim.performed_first_move
        assert victim.current_intent.move_type == MoveType.HEAL
        cs.player.hp = 80
        cs.end_turn()   # REATTACH
        assert victim.hp == 25
        assert not victim.retained_after_death
