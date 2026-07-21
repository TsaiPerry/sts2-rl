"""The SP2 conformance runner: replay a recording through the parity-sim.

Given a parsed `Recording` (recording.py) + `SaveOracle` (save.py), the runner
seeds a `RunState` from the recording's string seed, drives it act-by-act along
the recorded `MoveToMapCoord` path with a **force-win combat stub**, and diffs
the map/room-type walk + the four SP2 RNG-stream counters against the save.

Scope / deliberate accommodations (all counter-neutral):

  - **Combat is force-won.** SP2 leaves combat on the legacy `random.Random`;
    the stub ends each fight with the player alive so floors advance and the
    reward / unknown-room rolls still fire (spec: a stubbed combat rolls the
    same `Rewards` draws). The combat streams (shuffle, monster_ai, …) are
    therefore not compared.
  - **Neow is injected, not played.** The sim's Neow rolls its offer on the
    legacy RNG (out of SP2 scope), so it can't reproduce the recorded relics —
    yet the recorded free-travel relic (Winged Boots) is what makes the
    `MoveToMapCoord` indices valid. The runner skips the sim's Neow and grants
    exactly the relics the save says were picked there. Neow touches no parity
    stream, so this leaves every SP2 counter untouched.
  - **Only MAP/EVENT/REST decisions follow the recording.** Reward/shop/card
    selections get a safe default: which reward is *taken* is choice-independent
    for the parity streams (generation happens on room entry), so a default that
    always progresses suffices for SP2.

The runner returns a `ReplayResult` (divergences + live counters); the test
decides which counters to assert, so it can track the pre-Task-9 state (only
`UpFront` wired) and flip on `Rewards`/`Shops`/`UnknownMapPoint` once economy
parity lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..driver import (
    REST_HEAL,
    REST_LEAVE,
    REST_SMITH,
    DecisionKind,
    DecisionRequest,
    RunDriver,
)
from ..rng import PlayerRngType, RunRngType
from .comparators import Divergence, compare_counters, compare_node_type
from .recording import Command, Recording
from .save import SaveOracle


def short_act_name(act_id: str) -> str:
    """"ACT.OVERGROWTH" -> "overgrowth" (the sim's act_list keys)."""
    return act_id.split(".", 1)[-1].lower()


def relic_key(relic_id: str) -> str:
    """"RELIC.WINGED_BOOTS" -> "winged_boots" (the sim's relic ids)."""
    return relic_id.split(".", 1)[-1].lower()


class _CommandCursor:
    """A monotonic cursor over a recording's commands. `take(*names)` scans
    forward to the next command matching one of `names`, consuming (and
    discarding) everything before it — so combat commands and surplus reward
    lines are skipped automatically when the next map/event/rest decision is
    served."""

    def __init__(self, commands: list[Command]) -> None:
        self.commands = commands
        self.pos = 0

    def take(self, *names: str) -> Command | None:
        i = self.pos
        while i < len(self.commands):
            if self.commands[i].name in names:
                self.pos = i + 1
                return self.commands[i]
            i += 1
        return None


@dataclass
class ReplayResult:
    divergences: list[Divergence]
    run_counters: dict[RunRngType, int]
    player_counters: dict[PlayerRngType, int]
    rooms_walked: int
    reached_act_end: bool
    stopped_reason: str

    @property
    def ok(self) -> bool:
        return not self.divergences


# Rest-site option keys the recording uses (ChooseRestSiteOption arg).
_REST_BY_KEY = {"HEAL": REST_HEAL, "SMITH": REST_SMITH, "REST": REST_HEAL}


class _ForceWinDriver(RunDriver):
    """A RunDriver whose combat is a force-win stub and whose non-map decisions
    are served from a recording cursor (events/rest) or a safe default."""

    def __init__(self, run, cursor: _CommandCursor, **kwargs) -> None:
        self._cursor = cursor
        super().__init__(run, ask=self._ask_decision, include_neow=False, **kwargs)

    # ── force-win: end every fight with the player alive ─────────────────
    def _run_combat(self, encounter, room_type):
        from ..rewards import GOLD_REWARD_RANGES

        run = self.run
        combat = run.create_combat(encounter, room_type=room_type)
        self._combat = combat
        try:
            for enemy in combat.enemies:
                enemy.hp = 0
            if not combat.is_over:
                combat._end_combat(player_won=True)
        finally:
            self._combat = None
        run.finish_combat(combat, room_type=room_type)
        won = bool(combat.result and combat.result.player_won)
        if won and room_type in GOLD_REWARD_RANGES and encounter.should_give_rewards:
            self._offer_rewards(
                run.generate_combat_rewards(room_type, encounter=encounter))
        return combat

    # ── the decision seam for everything resolved inside a room ──────────
    def _ask_decision(self, request: DecisionRequest) -> int:
        legal = request.legal_actions()
        kind = request.kind
        if kind == DecisionKind.EVENT:
            return self._answer_event(request, legal)
        if kind == DecisionKind.REST:
            return self._answer_rest(request, legal)
        # Reward / shop / card-selection choices don't move the SP2 streams
        # (generation is choice-independent); take the first legal action,
        # which always progresses (skip a reward, leave a shop, pick a card).
        return legal[0]

    def _answer_event(self, request: DecisionRequest, legal: list[int]) -> int:
        cmd = self._cursor.take("ChooseEventOption")
        if cmd is None or not cmd.args:
            return legal[-1]  # no guidance: proceed/leave (usually last)
        raw = cmd.args[0]
        if raw == "-1":
            return legal[-1]
        try:
            idx = int(raw)
        except ValueError:
            return legal[0]
        return idx if idx in legal else legal[0]

    def _answer_rest(self, request: DecisionRequest, legal: list[int]) -> int:
        cmd = self._cursor.take("ChooseRestSiteOption")
        if cmd is not None and cmd.args:
            want = _REST_BY_KEY.get(cmd.args[0].upper())
            if want is not None and want in legal:
                return want
        return REST_LEAVE if REST_LEAVE in legal else legal[0]


class ReplayRunner:
    """Replay one recording/save pair through the parity-sim."""

    def __init__(self, recording: Recording, oracle: SaveOracle) -> None:
        self.recording = recording
        self.oracle = oracle

    def _neow_relics(self) -> list[str]:
        """The relics the save says were picked at the Act 1 Neow node."""
        history = self.oracle.map_history
        if not history or not history[0]:
            return []
        start = history[0][0]
        out: list[str] = []
        for stat in start.get("player_stats", []):
            for choice in stat.get("relic_choices", []):
                if choice.get("was_picked") and choice.get("choice"):
                    out.append(relic_key(choice["choice"]))
        return out

    def run(self, stop_after_act: int = 0) -> ReplayResult:
        """Drive the recording through act index `stop_after_act` (inclusive)
        and report divergences + the live SP2 stream counters."""
        from ..run import RunState

        rec = self.recording
        acts = [short_act_name(a) for a in rec.acts]
        run = RunState(string_seed=rec.seed)
        cursor = _CommandCursor(rec.commands)
        driver = _ForceWinDriver(run, cursor, acts=acts, ascension=rec.ascension)

        run.start_run(acts=acts, ascension=rec.ascension)
        driver._roll_shared_ancients()
        for rid in self._neow_relics():
            run.add_relic(rid)

        hist = self.oracle.map_history[0] if self.oracle.map_history else []
        divergences: list[Divergence] = []
        room_index = 1  # hist[0] is the (injected) Neow start node
        reached_act_end = False
        reason = "recording exhausted"

        while not run.at_run_end:
            cmd = cursor.take("MoveToMapCoord")
            if cmd is None or not cmd.args:
                reason = "no more MoveToMapCoord commands"
                break
            # `MoveToMapCoord {col}` (RunReplays MapMoveCommand): the arg is the
            # destination column; the row always advances one (current.row + 1).
            col = int(cmd.args[0])
            row = run.current_point.row + 1
            dest = next(
                (p for p in run.travelable_points()
                 if p.col == col and p.row == row),
                None,
            )
            if dest is None:
                divergences.append(Divergence(
                    "runner", room_index, f"(col={col}, row={row})", None,
                    "MoveToMapCoord destination not travelable",
                ))
                reason = "unreachable map coord"
                break
            resolution = run.enter_point(dest)
            if room_index < len(hist):
                d = compare_node_type(
                    room_index, hist[room_index].get("map_point_type", ""),
                    resolution.map_point_type,
                )
                if d is not None:
                    divergences.append(d)
            driver._resolve_room(resolution)
            room_index += 1
            if run.is_dead:
                reason = "player died"
                break
            if run.at_act_end:
                reached_act_end = True
                if run.act_index >= stop_after_act:
                    reason = f"reached act {run.act_index} boss"
                    break
                run.advance_act()
                driver._maybe_run_ancient()
                reached_act_end = False

        run_counters = run.rng_set.counters()
        player_counters = run.player_rng.counters()
        divergences.extend(
            compare_counters(run_counters, player_counters, self.oracle))
        return ReplayResult(
            divergences=divergences,
            run_counters=run_counters,
            player_counters=player_counters,
            rooms_walked=room_index - 1,
            reached_act_end=reached_act_end,
            stopped_reason=reason,
        )
