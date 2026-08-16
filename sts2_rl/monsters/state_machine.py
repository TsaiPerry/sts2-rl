"""Declarative monster move state machine, ported from STS2's
MonsterMoveStateMachine (src/Core/MonsterMoves/MonsterMoveStateMachine).

A monster's behaviour is a graph of states:

  MoveState             — a performable move (with the intent it telegraphs);
                          transitions to a fixed follow-up state.
  RandomBranchState     — weighted random chooser. Weights can be lambdas
                          (evaluated at roll time) and are zeroed by repeat
                          rules / cooldowns based on the machine's move log.
  ConditionalBranchState— first branch whose condition is true wins.

Rolling walks the graph from the current state until it lands on a MoveState;
branch states are invisible pass-throughs. The machine keeps a state_log of
every move taken, which is what powers the history-dependent randomness
(CANNOT_REPEAT, USE_ONLY_ONCE, cooldowns).
"""
from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING, Callable

from .base import Intent, Monster, MoveType

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem


def _weighted_roll(rng: random.Random, total: float) -> float:
    """RandomBranchState.GetNextState's exact primitive (RandomBranchState.cs:118):
    ``float num = rng.NextFloat(max)`` — ONE float32-precision draw scaled to
    [0, total), NOT WeightedNextItem (that's a different call with a different
    rounding path: NextFloat() then multiply, vs NextFloat(max) computing the
    scale inside the single draw). In parity mode `rng` is a GameRandomAdapter
    whose `.rng` is the raw game Rng, so route to its float32-exact
    `next_float(0, total)`; in legacy mode `rng` is the shared `random.Random`
    and we keep the existing `.random() * total` call (bit-identical to the
    pre-SP3 code — legacy behavior is intentionally unchanged)."""
    game_rng = getattr(rng, "rng", None)
    if game_rng is not None:
        return game_rng.next_float(0.0, total)
    return rng.random() * total


def weighted_branch_pick(rng: random.Random, items: list, weights: list[float]):
    """Game-exact single-NextFloat(total) weighted pick (the RandomBranchState
    primitive) for hand-rolled monsters not yet on the state machine. Mirrors
    RandomBranchState.get_next_state's roll+walk exactly: one _weighted_roll
    draw over the summed weights, then subtract-and-check-<=0 per item in
    order, falling back to the last item (matches RandomBranchState.cs:118-131
    byte-for-byte — same primitive the state-machine path uses)."""
    total = float(sum(weights))
    roll = _weighted_roll(rng, total)
    for item, weight in zip(items, weights):
        roll -= weight
        if roll <= 0:
            return item
    return items[-1]


# Creature.StunInternal (Creature.cs:535) names the synthetic stun move
# "STUNNED"; the combat loop and CreatureCmd.stun both recognise it by this id.
STUN_STATE_ID = "STUNNED"


def _stunned_move(ctx) -> None:
    """Body of the synthetic stun move. `CreatureCmd.Stun`'s `stunMove`
    argument (CreatureCmd.cs:884) is the caller's; every sim stun site passes
    none, so the perform body is empty — the point of performing it at all is
    MoveState.PerformMove setting `_performedAtLeastOnce`."""


# `MonsterModel.NextMove` is initialised to `new MoveState()`
# (MonsterModel.cs:239), and the parameterless ctor is
# `this("UNSET_MOVE", UnsetMove)` with NO intents (MoveState.cs:42-45). So a
# creature that has not been rolled yet is NOT null-moved in C# — it holds a
# real, performable, intent-less move. The sim needs the same object, because
# `AfterCreatureAdded` only rolls on the player side (CombatManager.cs:860-867)
# and an enemy-side spawn therefore sits on UNSET_MOVE until the next
# player-turn-start pass.
UNSET_STATE_ID = "UNSET_MOVE"


def _unset_move(ctx) -> None:
    """`MoveState.UnsetMove` (MoveState.cs:77-80) — the body THROWS
    `InvalidOperationException("No move has been set for the monster")`.

    Ported as a throw rather than softened to a no-op, because nothing can
    reach it in either engine and a raise is the cheaper tripwire if that ever
    stops being true: `ExecuteEnemyTurn` iterates `_state.Enemies.ToList()`, a
    snapshot taken before the first enemy acts (CombatManager.cs:1072), so a
    creature summoned part-way through the enemy turn does not act until the
    next one — by which time the player-turn-start pass has rolled it."""
    raise RuntimeError("No move has been set for the monster")


class MoveRepeatType(Enum):
    CAN_REPEAT_FOREVER = "can_repeat_forever"
    CAN_REPEAT_X_TIMES = "can_repeat_x_times"
    CANNOT_REPEAT = "cannot_repeat"
    USE_ONLY_ONCE = "use_only_once"


class MonsterState:
    """Base node in the move graph."""

    def __init__(self, state_id: str) -> None:
        self.id = state_id

    should_appear_in_logs = True
    is_move = False

    @property
    def can_transition_away(self) -> bool:
        return True

    def get_next_state(self, owner: MachineMonster, rng: random.Random) -> str | None:
        raise NotImplementedError

    def register_states(self, states: dict[str, MonsterState]) -> None:
        # C# RegisterStates is `monsterStates.Add(Id, this)` and Dictionary.Add
        # THROWS on a duplicate key (MoveState.cs:74 etc.) -- fail loudly here too
        # rather than silently letting a reused id redirect earlier follow_ups.
        if self.id in states and states[self.id] is not self:
            raise ValueError(
                f"duplicate state id {self.id!r} in the move graph: "
                f"{type(states[self.id]).__name__} and {type(self).__name__}"
            )
        states[self.id] = self

    def on_enter_state(self) -> None:
        pass

    def on_exit_state(self) -> None:
        pass


class MoveState(MonsterState):
    """A performable move: an on_perform callback plus the intent it shows.

    intent may be a static Intent or a zero-arg callable returning one (for
    moves whose telegraphed numbers depend on combat state).
    """

    is_move = True

    def __init__(
        self,
        state_id: str,
        on_perform: Callable[[CombatCtx], None],
        intent: Intent | Callable[[], Intent],
        must_perform_once_before_transitioning: bool = False,
    ) -> None:
        super().__init__(state_id)
        self._on_perform = on_perform
        self._intent = intent
        self.must_perform_once_before_transitioning = must_perform_once_before_transitioning
        self.follow_up: MonsterState | None = None
        # MoveState.cs:23 `FollowUpStateId` — the bare-id form of the same
        # link, resolved against the machine's state table at roll time.
        # GetNextState is `(FollowUpState?.Id ?? FollowUpStateId) ?? throw`
        # (MoveState.cs:67-70), so a monster can forward-reference a state
        # built later in GenerateMoveStateMachine without a two-pass build.
        self.follow_up_id: str | None = None
        self._performed_at_least_once = False

    @property
    def intent(self) -> Intent:
        return self._intent() if callable(self._intent) else self._intent

    @property
    def can_transition_away(self) -> bool:
        if self.must_perform_once_before_transitioning:
            return self._performed_at_least_once
        return True

    def perform(self, ctx: CombatCtx) -> None:
        self._performed_at_least_once = True
        self._on_perform(ctx)

    def on_exit_state(self) -> None:
        self._performed_at_least_once = False

    def get_next_state(self, owner: MachineMonster, rng: random.Random) -> str | None:
        # MoveState.cs:69 — the object link wins, the bare id is the fallback.
        if self.follow_up is not None:
            return self.follow_up.id
        if self.follow_up_id is not None:
            return self.follow_up_id
        raise RuntimeError(f"MoveState {self.id} has no follow-up state")


class RandomBranchState(MonsterState):
    """Weighted random chooser (mirrors RandomBranchState).

    Effective branch weight is computed at roll time from three inputs:
      - the base weight (a constant or a zero-arg lambda),
      - the repeat rule, which zeroes the weight based on the move log
        (CANNOT_REPEAT: not twice in a row; CAN_REPEAT_X_TIMES(n): not n+ in a
        row; USE_ONLY_ONCE: never after it has been used),
      - the cooldown, which zeroes the weight if the move appears in the last
        N logged moves.
    """

    should_appear_in_logs = False

    def __init__(self, state_id: str) -> None:
        super().__init__(state_id)
        self._branches: list[dict] = []

    def add_branch(
        self,
        state: MonsterState,
        weight: float | Callable[[], float] = 1.0,
        repeat_type: MoveRepeatType = MoveRepeatType.CAN_REPEAT_FOREVER,
        max_times: int | None = None,
        cooldown: int = 0,
    ) -> None:
        # RandomBranchState.cs's ten AddBranch overloads split into two families:
        # the `repeatType`-only overload (#1, :46-51) has no maxRepeats slot and
        # THROWS on CanRepeatXTimes; the `maxRepeats`-taking overloads always imply
        # CanRepeatXTimes and allow maxRepeats==0 (a permanently-disabled branch,
        # see `_effective_weight`). This one keyword signature distinguishes the
        # two by whether max_times was passed at all -- "disable forever" must be
        # spelled explicitly as max_times=0.
        if repeat_type is MoveRepeatType.CAN_REPEAT_X_TIMES and max_times is None:
            raise ValueError(
                f"add_branch({state.id!r}, ..., repeat_type=CAN_REPEAT_X_TIMES) "
                "requires an explicit max_times (RandomBranchState.cs:48-51 -- "
                "the repeatType-only overload has no maxRepeats slot and "
                "rejects CanRepeatXTimes there; pass max_times=0 if you mean "
                "a permanently-disabled branch)"
            )
        self._branches.append({
            "state_id": state.id,
            "weight": weight,
            "repeat_type": repeat_type,
            "max_times": 0 if max_times is None else max_times,
            "cooldown": cooldown,
        })

    def get_next_state(self, owner: MachineMonster, rng: random.Random) -> str | None:
        # RandomBranchState.cs:115-127: all-zero-weights is NOT special-cased --
        # `rng.NextFloat(0f)` burns a draw and returns 0f, so branch 0 wins via the
        # same loop as any other roll. Only real fall-through (float rounding
        # leaves every branch's remainder positive) reaches the THROW at :127.
        machine = owner.machine
        weights = [self._effective_weight(b, machine) for b in self._branches]
        total = sum(weights)
        roll = _weighted_roll(rng, total)
        for branch, weight in zip(self._branches, weights):
            roll -= weight
            if roll <= 0:
                return branch["state_id"]
        raise RuntimeError(f"No valid state found in RandomBranchState {self.id}!")

    @staticmethod
    def _effective_weight(branch: dict, machine: MonsterMoveStateMachine) -> float:
        log = machine.state_log
        state = machine.states[branch["state_id"]]
        repeat = branch["repeat_type"]

        allowed = 1.0
        if repeat is MoveRepeatType.USE_ONLY_ONCE:
            if state in log:
                allowed = 0.0
        elif repeat is not MoveRepeatType.CAN_REPEAT_FOREVER:
            # CANNOT_REPEAT is "at most 1 in a row"; X_TIMES is "at most n in a row"
            n = 1 if repeat is MoveRepeatType.CANNOT_REPEAT else branch["max_times"]
            if n <= 0:
                # RandomBranchState.cs:144-147 with maxTimes 0: num2 = 0, so
                # `num = (StateLog.Count < num2) ? 1 : 0` is 0 and the
                # while-loop's `num3 < num2` guard is false, so nothing can
                # revive it. The branch is PERMANENTLY DISABLED — the machine
                # is built and played with one fewer option, not rejected.
                allowed = 0.0
            else:
                allowed = 0.0 if len(log) >= n and all(s is state for s in log[-n:]) else 1.0

        if branch["cooldown"] > 0:
            recent_moves = [s for s in reversed(log) if s.is_move][: branch["cooldown"]]
            if any(m.id == branch["state_id"] for m in recent_moves):
                return 0.0

        base = branch["weight"]
        return allowed * (base() if callable(base) else base)


class ConditionalBranchState(MonsterState):
    """First branch whose condition returns True wins (mirrors ConditionalBranchState)."""

    should_appear_in_logs = False

    def __init__(self, state_id: str) -> None:
        super().__init__(state_id)
        self._branches: list[tuple[str, Callable[[], bool] | None]] = []

    def add_state(self, state: MonsterState, condition: Callable[[], bool] | None = None) -> None:
        """condition=None is an unconditional fallback (always taken if reached)."""
        self._branches.append((state.id, condition))

    def get_next_state(self, owner: MachineMonster, rng: random.Random) -> str | None:
        for state_id, condition in self._branches:
            if condition is None or condition():
                return state_id
        raise RuntimeError(f"No valid branch in ConditionalBranchState {self.id}")


class MonsterMoveStateMachine:
    def __init__(
        self,
        states: list[MonsterState],
        initial_state: MonsterState,
        unreachable_states: tuple[MonsterState, ...] = (),
    ) -> None:
        """`states` is the reachable graph (step 23: RegisterStates only adds
        the state itself, never what it points at, so every state a monster's
        graph can reach must be listed here explicitly).

        `unreachable_states` mirrors a shape the game itself ships:
        PhrogParasite.cs:39-52 builds a RandomBranchState ("RAND") with two
        CannotRepeat branches over INFECT/LASH, adds it to the SAME list
        RegisterStates walks (PhrogParasite.cs:51, `list.Add(randomBranchState)`)
        -- so it IS in `MonsterMoveStateMachine.States` -- and then never
        assigns it as anyone's FollowUpState and never passes it as
        `initialState`; INFECT and LASH FollowUp directly at each other
        instead (:45-46). A live, registered branch dispatcher the game
        built and then left permanently dead. RegisterStates performs no
        reachability check (MonsterMoveStateMachine.cs:20-25 just registers
        whatever it is handed), so C# does not need a second list to express
        this -- the sim does, because leaving an unwired state out of `states`
        already means something else here: NOT registering it at all (see
        Inklet.cs:69-81, where `INIT_RAND` is built and given branches but
        `list.Add` is never called on it, so it never reaches
        `GenerateMoveStateMachine`'s constructor call and never enters
        `States` -- a stricter case than PhrogParasite's, needing no
        machinery beyond simply not passing the object anywhere). Passing a
        state here registers it exactly as `states` does (same
        `register_states` call, same duplicate-id check) but keeps it out of
        every place that infers reachability; nothing else in `states` may
        point back at it, and this constructor does not check that (it has no
        graph-walk on either side, matching C#). A monster with nothing
        unreachable -- every port today -- passes nothing and gets identical
        behavior to before this parameter existed.
        """
        self.states: dict[str, MonsterState] = {}
        for state in states:
            state.register_states(self.states)
        for state in unreachable_states:
            state.register_states(self.states)
        self._initial_state = initial_state
        self.current: MonsterState = initial_state
        self._performed_first_move = False
        self.state_log: list[MonsterState] = []
        if self.current.should_appear_in_logs:
            self.state_log.append(self.current)

    def roll_move(self, owner: MachineMonster, rng: random.Random) -> MoveState:
        """Advance to the next MoveState and return it. The initial move is
        sticky: rolling before it has been performed returns it unchanged."""
        self._find_next_move_state(owner, rng)
        if not self.current.is_move:
            raise RuntimeError(f"{self.current.id} is not a valid move state")
        return self.current  # type: ignore[return-value]

    def force_current_state(self, state: MonsterState) -> None:
        """Externally override the current state (used by stuns/phase changes)."""
        self._set_current_state(state)

    def stun(self, next_move_id: str | None = None) -> MoveState:
        """Port of Creature.StunInternal (Creature.cs:524-544).

        A stun is a REAL move, not a flag: the game builds
        `new MoveState("STUNNED", stunMove, new StunIntent())` with
        `FollowUpStateId = nextMoveId` and
        `MustPerformOnceBeforeTransitioning = true` and force-sets it through
        SetMoveImmediate (MonsterModel.cs:420-432). `nextMoveId` defaults to
        `StateLog.Last().Id` — the last move the creature was telegraphing —
        so by default it REPEATS that move after the stunned turn, and the
        post-stun roll re-logs it (MonsterMoveStateMachine.cs:76-79).

        The synthetic state is deliberately not registered in `states`:
        ForceCurrentState does not call RegisterStates either.
        """
        if not next_move_id:
            next_move_id = self.state_log[-1].id
        state = MoveState(
            STUN_STATE_ID, _stunned_move, Intent(MoveType.STUN),
            must_perform_once_before_transitioning=True,
        )
        state.follow_up = self.states[next_move_id]
        self.force_current_state(state)
        return state

    def on_move_performed(self, move: MoveState) -> None:
        # MonsterModel.PerformMove (MonsterModel.cs:434-445) always sets
        # _performedAtLeastOnce before calling OnMovePerformed; mirror that here
        # too for callers that report a performed move without going through
        # MoveState.perform.
        move._performed_at_least_once = True
        self._performed_first_move = True

    def _find_next_move_state(self, owner: MachineMonster, rng: random.Random) -> None:
        if not self.current.can_transition_away or (
            not self._performed_first_move and self.current.is_move
        ):
            return
        logged: MonsterState | None = None
        while True:
            next_id = self.current.get_next_state(owner, rng)
            if next_id is not None and next_id not in self.states:
                raise RuntimeError(f"no valid state found: {next_id}")
            self._set_current_state(
                self._initial_state if next_id is None else self.states[next_id]
            )
            if logged is None and self.current.should_appear_in_logs:
                logged = self.current
            if self.current.is_move:
                break
        if logged is not None:
            self.state_log.append(logged)

    def _set_current_state(self, state: MonsterState) -> None:
        self.current.on_exit_state()
        self.current = state
        self.current.on_enter_state()


class MachineMonster(Monster):
    """Monster driven by a MonsterMoveStateMachine instead of hand-rolled
    _move_key logic. Subclasses implement build_machine().

    The next move is NOT rolled when the current one is performed: the game
    rolls every enemy's move in one pass at the top of the player's turn
    (CombatManager.cs:478-484 -> Creature.PrepareForNextTurn), which
    CombatState._roll_enemy_intents mirrors. The only roll outside that pass
    is the one CombatManager.AfterCreatureAdded (CombatManager.cs:860-867)
    makes when the creature joins the combat — and that one is SIDE-GATED:

        if (creature.IsEnemy && _state.CurrentSide == CombatSide.Player)
            creature.Monster.RollMove(...)

    so a creature summoned during the ENEMY side is not rolled at all. It
    keeps `MonsterModel.NextMove`'s initial `new MoveState()` — UNSET_MOVE —
    until the next player-turn-start pass reaches it in enemy-list order.
    Construction therefore does NOT roll here either; `CombatState
    .after_creature_added` owns the opening roll for both paths.
    """

    def __init__(self, hooks: HookSystem, rng: random.Random) -> None:
        super().__init__(hooks, rng)
        self._rng = rng
        self._machine: MonsterMoveStateMachine | None = None
        self.machine = self.build_machine()
        self._current_move: MoveState = MoveState(
            UNSET_STATE_ID, _unset_move, Intent(MoveType.UNKNOWN))

    @property
    def machine(self) -> MonsterMoveStateMachine:
        return self._machine  # type: ignore[return-value]

    @machine.setter
    def machine(self, value: MonsterMoveStateMachine) -> None:
        # MonsterModel.MoveStateMachine's setter (MonsterModel.cs:222-237) THROWS
        # if a machine is already set; only reset_state_machine() may clear one
        # first. Guard against a silent Python rebind losing state_log mid-combat.
        if self._machine is not None:
            raise RuntimeError(
                f"{type(self).__name__}'s move state machine has already "
                "been set"
            )
        self._machine = value

    def reset_state_machine(self) -> None:
        """Port of MonsterModel.ResetStateMachine (MonsterModel.cs:389-392):
        the ONLY way to clear an already-set machine, bypassing the setter's
        guard so a subsequent `self.machine = ...` (a SetUpForCombat-style
        rebuild) does not raise. Nothing calls this today -- no sim code path
        rebuilds a monster's machine mid-combat -- so it is dormant
        machinery, present for the same reason the C# method is: the setter
        guard is only useful once something CAN clear it."""
        self._machine = None

    def build_machine(self) -> MonsterMoveStateMachine:
        raise NotImplementedError

    @property
    def _move_rng(self) -> random.Random:
        # Move selection rolls happen on the MonsterAi stream (mirrors
        # MonsterModel.RollMove(targets) => MoveStateMachine.RollMove(...,
        # RunRng.MonsterAi)). self._rng (HP roll, and any non-move use a
        # subclass makes of it) is untouched — only the move roll moves.
        return self._hooks.combat.combat_rng.monster_ai

    @property
    def has_rolled_a_move(self) -> bool:
        return self._current_move.id != UNSET_STATE_ID

    @property
    def current_intent(self) -> Intent:
        if self.stunned:
            return Intent(MoveType.STUN)
        return self._current_move.intent

    def take_turn(self, ctx: CombatCtx) -> None:
        move = self._current_move
        move.perform(ctx)
        self.machine.on_move_performed(move)

    def telegraph_next_move(self) -> None:
        """Roll the next move (mirrors Creature.PrepareForNextTurn ->
        MonsterModel.RollMove). Called only from
        CombatState._roll_enemy_intents, the player-turn-start pass."""
        self._current_move = self.machine.roll_move(self, self._move_rng)
