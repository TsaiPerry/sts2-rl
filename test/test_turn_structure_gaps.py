"""The `seam/turn_structure` residues, round 5.

Each class here pins one named guard from `audit/records/seam/turn_structure.json`
against the decompiled source it cites. They are grouped by guard, not by
feature, because that is how the audit reads them back.

Run with:  py -m pytest test/test_turn_structure_gaps.py -v
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards.base import Card, CardRarity, CardType, TargetType
from sts2_rl.combat import Phase
from sts2_rl.turn_phase import PlayerTurnPhase


class _EtherealTurnEndCard(Card):
    """Ethereal AND HasTurnEndInHandEffect at once.

    No shipped card is both, which is why G15 was dormant; the divergence is
    in the engine, so the witness has to be synthetic.
    """

    id = "_test_ethereal_turn_end"
    name = "Ethereal Turn End"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.NONE
    is_ethereal = True
    has_turn_end_in_hand_effect = True
    max_upgrade_level = 0

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx, target_idx=None) -> None:
        pass

    def on_turn_end_in_hand(self, ctx) -> None:
        pass


class _NoEthereal:
    """A listener that vetoes every ethereal trigger."""

    def should_ethereal_trigger(self, card) -> bool:
        return False


class _PhaseSpy:
    """Records the player's PlayerTurnPhase as each hook fires."""

    def __init__(self, player):
        self.player = player
        self.seen: list[tuple[str, PlayerTurnPhase]] = []

    def _mark(self, name):
        self.seen.append((name, self.player.turn_phase))

    def before_side_turn_start(self, player):
        self._mark("before_side_turn_start")

    def on_block_cleared(self, creature):
        self._mark("on_block_cleared")

    def on_player_turn_started(self, player):
        self._mark("on_player_turn_started")

    def after_side_turn_start(self, player):
        self._mark("after_side_turn_start")

    def after_auto_pre_play_phase_entered(self, player):
        self._mark("after_auto_pre_play_phase_entered")

    def after_auto_post_play_phase_entered(self, player):
        self._mark("after_auto_post_play_phase_entered")

    def on_player_turn_end(self, player):
        self._mark("on_player_turn_end")

    def after_player_turn_end(self, player):
        self._mark("after_player_turn_end")

    def on_enemy_side_end(self):
        self._mark("on_enemy_side_end")


class TestG8ThePlayerTurnPhaseModel:
    """G8 — `PlayerTurnPhase` (PlayerTurnPhase.cs) is a real six-value model.

    C# moves every player through None -> Start -> AutoPrePlay -> Play ->
    AutoPostPlay -> End and back, and content READS it: Unceasing Top's
    `IsValidPhase` (UnceasingTop.cs:29-36) accepts exactly
    {AutoPrePlay, Play, AutoPostPlay}.
    """

    def test_the_enum_has_the_games_six_values_in_the_games_order(self):
        assert [p.name for p in PlayerTurnPhase] == [
            "NONE", "START", "AUTO_PRE_PLAY", "PLAY", "AUTO_POST_PLAY", "END",
        ]
        # UnceasingTop.cs:31 — `(uint)(phase - 2) <= 2u` only works on these
        # ordinals.
        assert [int(p) for p in PlayerTurnPhase] == [0, 1, 2, 3, 4, 5]

    def test_a_fresh_player_turn_walks_start_to_play(self):
        cs = CombatState(rng=random.Random(0))
        spy = _PhaseSpy(cs.player)
        cs.hooks.register(spy)
        cs.player.start_turn()
        assert spy.seen == [
            # CombatManager.cs:429 sets None, :464 sets Start AFTER
            # Hook.BeforeSideTurnStart.
            ("before_side_turn_start", PlayerTurnPhase.NONE),
            ("on_block_cleared", PlayerTurnPhase.START),
            ("on_player_turn_started", PlayerTurnPhase.START),
            ("after_side_turn_start", PlayerTurnPhase.START),
            # :616 — AutoPrePlay is entered for the hook and left again at :618.
            ("after_auto_pre_play_phase_entered", PlayerTurnPhase.AUTO_PRE_PLAY),
        ]
        assert cs.player.turn_phase is PlayerTurnPhase.PLAY

    def test_playing_a_card_happens_in_the_play_phase(self):
        cs = CombatState(rng=random.Random(0))
        assert cs.player.turn_phase is PlayerTurnPhase.PLAY

    def test_ending_the_turn_walks_auto_post_play_to_end_to_none(self):
        cs = CombatState(rng=random.Random(0))
        spy = _PhaseSpy(cs.player)
        cs.hooks.register(spy)
        cs.player.hp = 999
        cs.end_turn()
        by_name = dict(spy.seen)
        # :1165 — AutoPostPlay, entered strictly before Hook.BeforeTurnEnd.
        assert by_name["after_auto_post_play_phase_entered"] is PlayerTurnPhase.AUTO_POST_PLAY
        # :1175 — End, before Hook.BeforeTurnEnd at :1179.
        assert by_name["on_player_turn_end"] is PlayerTurnPhase.END
        assert by_name["after_player_turn_end"] is PlayerTurnPhase.END
        # :429 — the enemy's StartTurn puts every player back to None.
        assert by_name["on_enemy_side_end"] is PlayerTurnPhase.NONE

    def test_a_finished_combat_leaves_no_phase(self):
        """EndCombatInternal (CombatManager.cs:978) —
        `SetPhaseForAllPlayers(PlayerTurnPhase.None)`."""
        cs = CombatState(rng=random.Random(0))
        cs._end_combat(player_won=True)
        assert cs.player.turn_phase is PlayerTurnPhase.NONE


class TestPowerCmdG6DurationTicksRouteThroughModifyAmount:
    """power_cmd/G6's carried observation — the sim's duration ticks mutated
    `amount` directly, so `ModifyAmount`'s `IsEnding` guard never reached them.

    C#: `PowerCmd.TickDownDuration` (PowerCmd.cs:190-200) -> `Decrement`
    (:179-182) -> `ModifyAmount` (:215), which opens on
    `if (CombatManager.Instance.IsEnding) return 0` (:217-220).
    """

    def _vulnerable_enemy(self):
        from sts2_rl import PowerCmd, VulnerablePower

        cs = CombatState(rng=random.Random(0))
        PowerCmd.apply(cs.hooks, cs.enemies[0], VulnerablePower, 3)
        return cs, cs.enemies[0].powers["vulnerable"]

    def test_a_tick_in_the_ending_window_is_refused(self):
        cs, power = self._vulnerable_enemy()
        for e in cs.enemies:
            e.hp = 0
        assert cs.is_ending
        power._tick_duration()
        assert power.amount == 3

    def test_a_tick_in_a_live_combat_still_decrements(self):
        cs, power = self._vulnerable_enemy()
        power._tick_duration()
        assert power.amount == 2

    def test_the_last_tick_still_removes_the_power(self):
        """ModifyAmount's tail: `if (power.ShouldRemoveDueToAmount()) await
        Remove(power)` (PowerCmd.cs:247-250)."""
        cs, power = self._vulnerable_enemy()
        power.amount = 1
        power._tick_duration()
        assert "vulnerable" not in cs.enemies[0].powers

    def test_skip_next_tick_is_still_honoured_before_the_guard(self):
        """TickDownDuration consumes SkipNextDurationTick and returns WITHOUT
        calling Decrement (PowerCmd.cs:192-195), so the guard is never
        reached on a skipped tick."""
        cs, power = self._vulnerable_enemy()
        power.skip_next_tick = True
        power._tick_duration()
        assert power.amount == 3 and not power.skip_next_tick


class TestN4RoundNumberIsNotTurnNumber:
    """N4 — `CombatState.RoundNumber` and `PlayerCombatState.TurnNumber` are
    two counters, and SwitchSides (CombatManager.cs:1398-1419) advances them
    differently: on an EXTRA player turn only `IncrementTurnNumber()` runs
    (:1417); `RoundNumber++` (:1413) is on the normal-round branch alone.

    `AbstractModel.cs:1125` directs content to use AfterSideTurnStart "with a
    RoundNumber check", so the two are meant to be distinguishable, and
    CombatHistory stamps every entry with RoundNumber (CombatHistory.cs:40-120).
    """

    class _ExtraTurn:
        def __init__(self, times=1):
            self.left = times

        def should_take_extra_turn(self, player):
            if self.left:
                self.left -= 1
                return True
            return False

    def test_both_start_at_one(self):
        """CombatState.cs:156 — `RoundNumber = 1`."""
        cs = CombatState(rng=random.Random(0))
        assert cs.turn == 1 and cs.round_number == 1

    def test_a_normal_round_advances_both(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.end_turn()
        assert cs.turn == 2 and cs.round_number == 2

    def test_an_extra_turn_advances_only_the_turn_number(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.hooks.register(self._ExtraTurn())
        cs.end_turn()
        assert cs.turn == 2
        assert cs.round_number == 1
        # ...and the next, normal, end of turn advances both again.
        cs.end_turn()
        assert cs.turn == 3 and cs.round_number == 2

    def test_history_is_stamped_with_the_round_number(self):
        """CombatHistory.cs:40 — `new CardPlayStartedEntry(cardPlay,
        combatState.RoundNumber, ...)`. An extra turn is the SAME round, so
        "this turn" queries still see the earlier plays."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.hooks.register(self._ExtraTurn())
        strike = next(i for i, c in enumerate(cs.player.hand) if c.id == "strike")
        cs.play_card(strike, 0)
        played_before = cs.history.attack_plays_this_turn()
        assert played_before == 1
        cs.end_turn()
        assert cs.history.attack_plays_this_turn() == played_before


class TestG10TheCombatEndPath:
    """G10 — the combat-end path keeps C#'s distinctions.

    `CheckWinCondition` (CombatManager.cs:1046-1059) has TWO exits and they are
    not symmetric. `ProcessPendingLoss` (:956-965) sets `IsInProgress = false`
    and fires **no hook at all**. `EndCombatInternal` (:970-1030) revives every
    dead player to 1 HP (:986), then fires `Hook.AfterCombatEnd` (:988), then
    `Hook.AfterCombatVictory` (:999). The sim collapsed all of that into one
    `on_combat_end(player_won)` fired on both outcomes.
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

    def test_a_win_fires_after_combat_end_then_after_combat_victory(self):
        cs = CombatState(rng=random.Random(0))
        w = self._Watch()
        cs.hooks.register(w)
        for e in cs.enemies:
            e.hp = 0
        cs._check_win_condition()
        assert cs.result.player_won
        # Hook.cs:340-352 makes two complete passes, Early first.
        assert w.seen == ["end", "victory_early", "victory"]

    def test_a_loss_fires_nothing(self):
        """ProcessPendingLoss (CombatManager.cs:956-965) — no hook. The sim
        fired the victory hook with `player_won=False`, so a relic that
        guarded on the flag was merely lucky and one that did not was wrong."""
        cs = CombatState(rng=random.Random(0))
        w = self._Watch()
        cs.hooks.register(w)
        cs.player.hp = 0
        cs._check_win_condition()
        assert cs.result is not None and not cs.result.player_won
        assert w.seen == []

    def test_a_loss_is_deferred_until_the_next_check(self):
        """LoseCombat (CombatManager.cs:945-951) only MARKS the loss; :942-943
        says why — "the actual loss processing happens at the next safe point
        (in CheckWinCondition) to avoid race conditions where effects try to
        run after IsInProgress is false"."""
        cs = CombatState(rng=random.Random(0))
        cs.lose_combat()
        assert cs.phase is Phase.PLAYER_TURN     # not processed yet...
        assert cs.is_ending                      # ...but the fight is ending
        cs._check_win_condition()
        assert cs.phase is Phase.COMBAT_OVER
        assert not cs.result.player_won

    def test_a_dead_player_is_revived_before_the_victory_hooks(self):
        """Player.ReviveBeforeCombatEnd (Player.cs:821-827) heals a dead player
        to 1. Player.cs:816-819 says why it must happen BEFORE the hooks: "If
        the player is still dead during HookBus.AfterCombatEnd, their relics
        will not be subscribed to the HookBus"."""
        hp_at_hook = {}

        class Watch:
            def on_combat_end(self):
                hp_at_hook["end"] = cs.player.hp

        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(Watch())
        cs.player.hp = 0
        for e in cs.enemies:
            e.hp = 0
        # A win reached with the player at 0: the pending-loss arm is not
        # armed, so CheckWinCondition takes the EndCombatInternal branch.
        cs._end_combat(player_won=True)
        assert hp_at_hook["end"] == 1
        assert cs.player.hp == 1

    def test_the_loss_arm_wins_a_tie(self):
        """CheckWinCondition tests `_pendingLoss` FIRST (:1048)."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 0
        for e in cs.enemies:
            e.hp = 0
        cs._check_win_condition()
        assert not cs.result.player_won


class _KillsOn:
    """A listener that drops the last enemy (or the player) to 0 HP on one
    named hook, WITHOUT routing through _end_combat -- the shape a real
    turn-end effect has."""

    def __init__(self, cs, hook, victim="enemies"):
        self.cs = cs
        self.victim = victim
        setattr(self, hook, self._fire)

    def _fire(self, *a, **kw):
        if self.victim == "enemies":
            for e in self.cs.enemies:
                e.hp = 0
        else:
            self.cs.player.hp = 0


class TestG13TheWinConditionIsRecomputed:
    """G13 — `CheckWinCondition` (CombatManager.cs:1046-1059) at all six sites.

    It is a RECOMPUTATION: `_pendingLoss != null` or `IsEnding`. The sim's
    mid-pipeline "checks" read the cached `phase` instead, so a listener that
    killed the last enemy without routing through `_end_combat` went unnoticed
    until the next site that did recompute.
    """

    def test_a_kill_from_hook_before_turn_end_stops_the_pipeline_there(self):
        """CombatManager.cs:1181 — `if (await CheckWinCondition()) return;`,
        immediately after Hook.BeforeTurnEnd and BEFORE DoTurnEnd. A Burn in
        hand must not get to deal its damage."""
        from sts2_rl.cards import make_card

        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.player.hand.append(make_card("burn"))
        hp_before = cs.player.hp
        cs.hooks.register(_KillsOn(cs, "on_player_turn_end"))
        cs.end_turn()
        assert cs.phase is Phase.COMBAT_OVER
        assert cs.result.player_won
        assert cs.player.hp == hp_before

    def test_a_kill_from_a_turn_end_card_stops_before_the_flush(self):
        """CombatManager.cs:1207-1208 — the check that closes
        EndPlayerTurnPhaseOneInternal, so phase two (the flush) never runs."""
        from sts2_rl.cards import make_card

        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        held = list(cs.player.hand)
        burn = make_card("burn")
        burn.combat = cs
        cs.player.hand.append(burn)
        # Burn resolves its turn-end effect and is discarded; the discard is
        # what fires the kill, so the fight ends inside DoTurnEnd.
        cs.hooks.register(_KillsOn(cs, "on_card_discarded"))
        cs.end_turn()
        assert cs.phase is Phase.COMBAT_OVER
        assert cs.player.hand == held

    def test_a_kill_from_the_enemy_side_end_is_caught(self):
        """CombatManager.cs:830 — EndEnemyTurn checks after
        EndEnemyTurnInternal and only then switches sides."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.hooks.register(_KillsOn(cs, "on_enemy_side_end"))
        turn_before = cs.turn
        cs.end_turn()
        assert cs.phase is Phase.COMBAT_OVER
        # ...and no fresh player turn was handed out.
        assert cs.turn == turn_before

    def test_a_player_death_from_the_enemy_side_end_is_caught(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        cs.hooks.register(_KillsOn(cs, "on_enemy_side_end", victim="player"))
        cs.end_turn()
        assert cs.phase is Phase.COMBAT_OVER
        assert not cs.result.player_won


class TestG13DeadPlayerGuards:
    def test_setup_player_turn_returns_early_for_a_dead_player(self):
        """SetupPlayerTurn (CombatManager.cs:631-634) — `if
        (player.Creature.IsDead) return;`, so no energy, no draw and no
        Hook.AfterPlayerTurnStart. The side hooks around it still run."""
        seen: list[str] = []

        class Watch:
            def before_side_turn_start(self, player):
                seen.append("before_side_turn_start")

            def on_energy_reset(self, player):
                seen.append("on_energy_reset")

            def on_player_turn_started(self, player):
                seen.append("on_player_turn_started")

            def after_side_turn_start(self, player):
                seen.append("after_side_turn_start")

            def after_auto_pre_play_phase_entered(self, player):
                seen.append("after_auto_pre_play_phase_entered")

        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(Watch())
        cs.player.hand.clear()
        cs.player.hp = 0
        cs.player.start_turn()
        assert seen == ["before_side_turn_start", "after_side_turn_start"]
        assert cs.player.hand == []

    def test_flush_player_hand_returns_early_for_a_dead_player(self):
        """FlushPlayerHand (CombatManager.cs:1315-1318) — the whole method,
        including its EndOfTurnCleanup tail.

        No separate guard is needed in the sim: with one player a dead player
        makes `IsEnding` true by the pending-loss arm, so `discard_hand`'s
        `IsOverOrEnding` guard (CardCmd.cs:174-177) already covers it. This
        pins the OBSERVABLE behaviour, which is what step 60 asks for."""
        cs = CombatState(rng=random.Random(0))
        held = list(cs.player.hand)
        card = held[0]
        card.add_cost_this_turn(-1)
        cs.player.hp = 0
        cs.player.discard_hand()
        assert cs.player.hand == held           # nothing flushed
        assert card._cost_delta_this_turn == -1  # nor cleaned up


class TestG7EndOfTurnCleanup:
    """G7 — `PlayerCombatState.EndOfTurnCleanup` (PlayerCombatState.cs:268-274).

    Per card in EVERY pile it clears ExhaustOnNextPlay, HasSingleTurnRetain,
    HasSingleTurnSly and the turn-scoped cost modifiers (CardModel.cs:1610-1623,
    CardEnergyCost.cs:331-335). It runs TWICE a round -- at the end of the enemy
    turn for every player (CombatManager.cs:1254) and inside each player's
    FlushPlayerHand (:1346). The sim's only per-turn card reset cleared the cost
    modifiers alone, and did it at the START of the next player turn, so the
    window was a full enemy turn too wide.
    """

    def test_the_flush_site_clears_a_turn_cost_modifier(self):
        """CombatManager.cs:1346 — inside FlushPlayerHand, after
        Hook.AfterFlush."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.hand[0]
        card.add_cost_this_turn(-1)
        base = card._energy_cost
        assert card.energy_cost == max(0, base - 1)
        cs.player.discard_hand()
        assert card.energy_cost == base

    def test_it_reaches_cards_in_every_pile(self):
        """`foreach (CardModel allCard in AllCards)` — not just the hand."""
        cs = CombatState(rng=random.Random(0))
        buried = cs.player.draw_pile[0]
        buried.set_free_this_turn()
        assert buried.energy_cost == 0
        cs.player.end_of_turn_cleanup()
        assert buried.energy_cost == buried._energy_cost

    def test_the_modifier_expires_at_turn_end_not_next_turn_start(self):
        """The window the sim used to have was a full enemy turn too wide: a
        cost cut applied on turn N still applied all through the enemy turn."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        card = cs.player.draw_pile[0]
        card.add_cost_this_turn(-1)
        base = card._energy_cost

        seen = {}

        class Watch:
            def on_enemy_side_end(self):
                seen["during_enemy_turn"] = card.energy_cost

        cs.hooks.register(Watch())
        cs.end_turn()
        assert seen["during_enemy_turn"] == base

    def test_single_turn_retain_keeps_a_card_then_expires(self):
        """CardModel.GiveSingleTurnRetain (:1347-1350) + ShouldRetainThisTurn
        (:590-600) — "Will be cleared at the end of the turn"."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.hand[0]
        assert not card.retain                      # no Retain keyword
        card.give_single_turn_retain()
        assert card.should_retain_this_turn
        cs.player.discard_hand()
        assert card in cs.player.hand               # retained by the flush...
        assert not card.should_retain_this_turn     # ...and cleared by the tail

    def test_single_turn_sly_expires(self):
        """CardModel.GiveSingleTurnSly (:1356-1359). Nothing in the sim grants
        or reads Sly yet; the STATE exists because EndOfTurnCleanup's job is to
        clear it."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.hand[0]
        card.give_single_turn_sly()
        assert card.is_sly_this_turn
        cs.player.end_of_turn_cleanup()
        assert not card.is_sly_this_turn

    def test_exhaust_on_next_play_makes_one_play_exhaust_then_clears(self):
        """CardModel.cs:2076-2078 — the exhaust decision consumes the flag."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.hand[0]
        assert not card.exhausts
        card.exhaust_on_next_play = True
        idx = cs.player.hand.index(card)
        cs.play_card(idx, 0)
        assert card in cs.player.exhaust_pile
        assert not card.exhaust_on_next_play

    def test_the_enemy_side_site_also_clears(self):
        """CombatManager.cs:1252-1255 — EndEnemyTurnInternal runs it for every
        player, BETWEEN Hook.BeforeTurnEnd and Hook.AfterTurnEnd."""
        cs = CombatState(rng=random.Random(0))
        card = cs.player.draw_pile[0]
        order: list[str] = []

        class Watch:
            def before_enemy_side_end(self):
                card.give_single_turn_retain()
                order.append(f"before:{card.should_retain_this_turn}")

            def on_enemy_side_end(self):
                order.append(f"after:{card.should_retain_this_turn}")

        cs.hooks.register(Watch())
        cs.player.hp = 999
        cs.end_turn()
        assert order == ["before:True", "after:False"]


class TestN1TheTurnSetupRaceGuard:
    """N1 — `_inPlayerTurnSetup` / `_deferredEndTurnTransition`
    (CombatManager.cs:702-714, 722-735).

    The machinery exists exactly so a card auto-played during the AutoPrePlay
    phase can end the turn without the transition racing the tail of StartTurn:
    `SetReadyToEndTurn` stores the transition instead of running it, and
    `ReleaseDeferredEndTurnTransitionIfNeeded` runs it on every exit path of the
    setup. The sim's `start_turn` is synchronous, so an `end_turn` re-entered
    from inside it would have recursed.
    """

    class _EndsTurnDuringSetup:
        def __init__(self, cs):
            self.cs = cs
            self.turn_when_called = None
            self.turn_right_after_the_call = None
            self.ready_right_after_the_call = None

        def after_auto_pre_play_phase_entered(self, player):
            self.turn_when_called = self.cs.turn
            self.cs.end_turn()
            self.turn_right_after_the_call = self.cs.turn
            self.ready_right_after_the_call = self.cs.is_player_ready_to_end_turn

    def test_an_end_turn_from_inside_setup_is_deferred_not_recursed(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        spy = self._EndsTurnDuringSetup(cs)
        cs.hooks.register(spy)
        turn_before = cs.turn
        cs._start_player_turn()
        # Inside the window, nothing moved...
        assert spy.turn_right_after_the_call == spy.turn_when_called
        # ...and the moment setup exits, the stored transition runs.
        assert cs.turn > turn_before

    def test_readiness_is_observable_from_the_moment_of_the_deferral(self):
        """`IsPlayerReadyToEndTurn` (CombatManager.cs:686-698) — with a single
        player, `AllPlayersReadyToEndTurn()` is true as soon as that player
        readies, so the deferral and the readiness are the same instant."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        spy = self._EndsTurnDuringSetup(cs)
        cs.hooks.register(spy)
        assert not cs.is_player_ready_to_end_turn
        cs._start_player_turn()
        assert spy.ready_right_after_the_call is True
        # ...and it is cleared again by the release.
        assert not cs.is_player_ready_to_end_turn

    def test_outside_setup_end_turn_is_immediate(self):
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 999
        turn_before = cs.turn
        cs.end_turn()
        assert cs.turn > turn_before
        assert not cs.is_player_ready_to_end_turn

    def test_whispering_earring_stops_once_the_turn_is_readied(self):
        """WhisperingEarring.cs:63-66 — the auto-play loop's SECOND break is
        `IsPlayerReadyToEndTurn(player)`, which only becomes reachable once the
        deferral exists. The sim's loop had no such check."""
        from sts2_rl.relics import make_relic

        earring = make_relic("whispering_earring")
        cs = CombatState(rng=random.Random(0), relics=[earring])
        cs.turn = 1
        hand_before = list(cs.player.hand)
        cs._deferred_end_turn_transition = lambda: None
        earring.after_auto_pre_play_phase_entered_late(cs.player)
        assert cs.player.hand == hand_before


class _HandEmptySpy:
    def __init__(self):
        self.count = 0

    def on_hand_emptied(self, player):
        self.count += 1


class TestG16WhereTheHandEmptyCheckRuns:
    """G16 — `CombatManager.CheckForEmptyHand` has exactly two callers.

    CombatManager.cs:880-883 spells the rule out: "we manually check after a
    card is played, and after a potion is used, since these are the two ways a
    player can manually interact with combat state (besides ending turn, which
    should not trigger an empty hand check)". The sim fired it from the
    end-of-turn flush -- the excluded site -- and from nowhere else.
    """

    def test_playing_the_last_card_fires_it(self):
        """CardModel.cs:1992, after the result-pile move."""
        cs = CombatState(rng=random.Random(0))
        spy = _HandEmptySpy()
        cs.hooks.register(spy)
        from sts2_rl.cards import make_card

        card = make_card("defend")
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs.play_card(0)
        assert spy.count == 1

    def test_the_flush_does_not_fire_it(self):
        """CombatManager.cs:882 — "besides ending turn, which should not
        trigger an empty hand check"."""
        cs = CombatState(rng=random.Random(0))
        spy = _HandEmptySpy()
        cs.hooks.register(spy)
        cs.player.hp = 999
        cs.player.discard_hand()
        assert spy.count == 0

    def test_a_mid_effect_empty_hand_does_not_fire_it(self):
        """`!IsExecutingCardOrPotionEffect(player)` (CombatManager.cs:889).

        The docstring's own worked example: Unceasing Top plus a last card
        that draws. Without the depth guard the hand looks empty the instant
        the card leaves it, and the check fires twice.
        """
        cs = CombatState(rng=random.Random(0))
        spy = _HandEmptySpy()
        cs.hooks.register(spy)
        from sts2_rl.cards import make_card

        card = make_card("pommel_strike")
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs.play_card(0, 0)
        # Pommel Strike drew, so the hand is NOT empty when the check runs --
        # and the mid-OnPlay moment when it was empty must not have counted.
        assert spy.count == 0

    def test_using_a_potion_still_fires_it(self):
        """PotionModel.cs:340 — unchanged by this round."""
        from sts2_rl.potions import make_potion

        cs = CombatState(rng=random.Random(0), potions=[make_potion("block_potion")])
        spy = _HandEmptySpy()
        cs.hooks.register(spy)
        cs.player.hand.clear()
        assert cs.use_potion(0)
        assert spy.count == 1


class TestG16UnceasingTopIsOnItsRealHook:
    """UnceasingTop.cs:16-36 — `AfterHandEmptied`, gated on
    `IsValidPhase(player.PlayerCombatState.Phase)`, which is exactly
    {AutoPrePlay, Play, AutoPostPlay}. The sim's port compensated for the
    missing call site by living on `on_card_played`."""

    def _with_top(self):
        from sts2_rl.relics import make_relic

        top = make_relic("unceasing_top")
        cs = CombatState(rng=random.Random(0), relics=[top])
        cs.player.hand.clear()
        return cs, top

    def test_it_listens_on_hand_emptied(self):
        cs, top = self._with_top()
        assert hasattr(top, "on_hand_emptied")
        assert not hasattr(top, "on_card_played")

    def test_it_draws_when_the_last_card_is_played(self):
        from sts2_rl.cards import make_card

        cs, top = self._with_top()
        cs.player.hand.append(make_card("defend"))
        before = len(cs.player.draw_pile)
        cs.play_card(0)
        assert len(cs.player.hand) == 1
        assert len(cs.player.draw_pile) == before - 1

    def test_it_does_not_draw_outside_its_phases(self):
        """UnceasingTop.cs:26-28 — "Don't trigger before hand draw or after
        hand flush, because if a card is autoplayed during this time, the
        player's hand will always be empty, so Unceasing Top will always
        draw"."""
        cs, top = self._with_top()
        cs.player.turn_phase = PlayerTurnPhase.START
        before = len(cs.player.hand)
        cs.hooks.on_hand_emptied(cs.player)
        assert len(cs.player.hand) == before

        cs.player.turn_phase = PlayerTurnPhase.END
        cs.hooks.on_hand_emptied(cs.player)
        assert len(cs.player.hand) == before


class TestG16JossPaperIsOnItsRealHook:
    """JossPaper.cs:116-124 — the deferred Ethereal credit is
    `AfterSideTurnEnd` (Hook.AfterTurnEnd, CombatManager.cs:1307), gated on
    `participants.Contains(Owner.Creature)`. The sim hung it on
    `on_hand_emptied`, which is a different hook that happened to fire from
    inside the flush."""

    def test_it_listens_on_after_player_turn_end(self):
        from sts2_rl.relics import make_relic

        joss = make_relic("joss_paper")
        assert hasattr(joss, "after_player_turn_end")
        assert not hasattr(joss, "on_hand_emptied")

    def test_ethereal_exhausts_are_credited_after_the_flush(self):
        from sts2_rl.cards import make_card
        from sts2_rl.relics import make_relic

        joss = make_relic("joss_paper")
        cs = CombatState(rng=random.Random(0), relics=[joss])
        joss.cards_exhausted = 4
        cs.player.hand.clear()
        cs.player.hand.append(make_card("dazed"))
        cs.player.hp = 999
        before = len(cs.player.draw_pile)
        cs.end_turn()
        # The Ethereal Dazed took the count to 5 and drew one card, and the
        # draw landed AFTER the flush -- so it is still in hand.
        assert joss.cards_exhausted == 0
        assert len(cs.player.draw_pile) < before


class TestG15EtherealWrapperDoesNotReconsult:
    """G15 — `CardModel.OnTurnEndInHandWrapper` decides on the raw keyword.

    `Hook.ShouldEtherealTrigger` is consulted exactly once per turn end, in
    `DoTurnEnd`'s partition (CombatManager.cs:1233), and only for the cards
    that have NO turn-end effect. The wrapper that runs for the cards that DO
    have one tests `Keywords.Contains(CardKeyword.Ethereal)` and nothing else
    (CardModel.cs:1690).
    """

    def _end_turn_holding(self, card, *, veto: bool):
        cs = CombatState(rng=random.Random(0))
        if veto:
            cs.hooks.register(_NoEthereal())
        cs.player.hand.clear()
        cs.player.hand.append(card)
        card.combat = cs
        cs._process_turn_end_cards()
        return cs

    def test_a_vetoed_ethereal_turn_end_card_still_exhausts(self):
        card = _EtherealTurnEndCard()
        cs = self._end_turn_holding(card, veto=True)
        assert card in cs.player.exhaust_pile
        assert card not in cs.player.discard_pile

    def test_a_vetoed_ethereal_card_with_no_turn_end_effect_is_spared(self):
        """The partition's own consult (CombatManager.cs:1233) is untouched:
        a vetoed card with no turn-end effect stays in hand for the flush."""
        from sts2_rl.cards import make_card

        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(_NoEthereal())
        card = make_card("dazed")
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs._process_turn_end_cards()
        assert card in cs.player.hand
        assert card not in cs.player.exhaust_pile

    def test_an_unvetoed_ethereal_turn_end_card_exhausts(self):
        card = _EtherealTurnEndCard()
        cs = self._end_turn_holding(card, veto=False)
        assert card in cs.player.exhaust_pile

    def test_the_exhaust_is_flagged_caused_by_ethereal(self):
        """CardModel.cs:1692 — `causedByEthereal: true`, which is what Joss
        Paper reads."""
        seen: list[tuple] = []

        class Watch:
            def on_card_exhausted(self, card, caused_by_ethereal=False):
                seen.append((card, caused_by_ethereal))

        card = _EtherealTurnEndCard()
        cs = CombatState(rng=random.Random(0))
        cs.hooks.register(Watch())
        cs.hooks.register(_NoEthereal())
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs._process_turn_end_cards()
        assert seen == [(card, True)]
