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
from .combat_driver import _COMBAT_CMDS, _COMBAT_TAIL_CMDS, ReplayCombatDriver
from .comparators import (
    SP3_COMBAT_STREAMS,
    Divergence,
    compare_counters,
    compare_node_type,
)
from .recording import Command, Recording
from .save import SaveOracle


def short_act_name(act_id: str) -> str:
    """"ACT.OVERGROWTH" -> "overgrowth" (the sim's act_list keys)."""
    return act_id.split(".", 1)[-1].lower()


def relic_key(relic_id: str) -> str:
    """"RELIC.WINGED_BOOTS" -> "winged_boots" (the sim's relic ids)."""
    return relic_id.split(".", 1)[-1].lower()


_ALL_RELIC_IDS: frozenset[str] | None = None


def _all_relic_ids() -> frozenset[str]:
    """The set of ported relic ids (ALL_RELICS keys), cached."""
    global _ALL_RELIC_IDS
    if _ALL_RELIC_IDS is None:
        from ..relics import ALL_RELICS
        _ALL_RELIC_IDS = frozenset(ALL_RELICS)
    return _ALL_RELIC_IDS


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

    def peek(self) -> Command | None:
        """Non-consuming: the next command, or None at end of recording."""
        return self.commands[self.pos] if self.pos < len(self.commands) else None

    def advance(self) -> None:
        """Consume exactly the command `peek()` just returned."""
        self.pos += 1

    def take_before(self, name: str, stops: frozenset[str]) -> Command | None:
        """Scan forward for the next `name` command, but stop (without
        consuming anything) if a command in `stops` is reached first. Used to
        bound a post-combat reward lookahead to its own room: a `TakeCard` that
        belongs to this fight's reward precedes the next room decision, whereas
        a skipped card leaves the next `stops` boundary as the very next hit."""
        i = self.pos
        while i < len(self.commands):
            cn = self.commands[i].name
            if cn == name:
                self.pos = i + 1
                return self.commands[i]
            if cn in stops:
                return None
            i += 1
        return None

    def skip_while(self, names: frozenset[str]) -> None:
        """Advance past every immediately-following command whose name is in
        `names` (no-op if the next command isn't one). Used to drop a fight's
        unreplayed tail when the combat driver stops mid-fight, so the cursor
        lands on the post-combat reward/room boundary."""
        while self.pos < len(self.commands) and self.commands[self.pos].name in names:
            self.pos += 1

    def take_first_of(self, names: frozenset[str], stops: frozenset[str]) -> Command | None:
        """Like `take_before`, but matches any of `names` (bounded by `stops`).
        Used to serve one shop-purchase command per shop-loop iteration."""
        i = self.pos
        while i < len(self.commands):
            cn = self.commands[i].name
            if cn in names:
                self.pos = i + 1
                return self.commands[i]
            if cn in stops:
                return None
            i += 1
        return None


# Commands that open a new room decision — the boundary a post-combat reward
# lookahead must not scan past (else it would steal the NEXT fight's TakeCard).
_ROOM_BOUNDARY = frozenset(
    {"MoveToMapCoord", "ChooseEventOption", "ChooseRestSiteOption",
     "PlayCard", "EndTurn", "UsePotion"}
)


@dataclass
class ReplayResult:
    divergences: list[Divergence]
    run_counters: dict[RunRngType, int]
    player_counters: dict[PlayerRngType, int]
    rooms_walked: int
    reached_act_end: bool
    stopped_reason: str
    # SP3: combat is diffed as its own subsystem. `combat_divergences` holds
    # per-command Hand/Enemies mismatches plus the combat-stream counter diffs;
    # `unresolved_play_card_ids` lists recorded PlayCard ids that never resolved
    # to a live card. Kept separate from `divergences` (SP2 map/economy) so
    # `ok` — and the SP2 conformance tests — stay combat-agnostic until Task 9.
    combat_divergences: list[Divergence] = field(default_factory=list)
    unresolved_play_card_ids: list[int] = field(default_factory=list)
    forced_combats: int = 0

    @property
    def ok(self) -> bool:
        return not self.divergences

    @property
    def combat_ok(self) -> bool:
        return not self.combat_divergences and not self.unresolved_play_card_ids


# Rest-site option keys the recording uses (ChooseRestSiteOption arg).
_REST_BY_KEY = {"HEAL": REST_HEAL, "SMITH": REST_SMITH, "REST": REST_HEAL}

# Shop-purchase commands the recording emits inside an OpenShop..MoveToMapCoord
# block (one per shop-loop iteration).
_SHOP_CMDS = frozenset({"BuyCard", "BuyRelic", "BuyPotion", "BuyCardRemoval"})


class _ForceWinDriver(RunDriver):
    """A RunDriver whose combat is a force-win stub and whose non-map decisions
    are served from a recording cursor (events/rest) or a safe default."""

    def __init__(self, run, cursor: _CommandCursor, **kwargs) -> None:
        self._cursor = cursor
        # SP3 combat accumulators (across every fight in the run).
        self.combat_divergences: list[Divergence] = []
        self.unresolved_play_card_ids: list[int] = []
        self.forced_combats = 0
        # The out-of-combat card-grid screen currently being served: the picks
        # left over from its one `SelectGridCard` command, and the
        # count_remaining its next ask will carry (see _answer_select_grid).
        self._grid_picks: list = []
        self._grid_open: int | None = None
        super().__init__(run, ask=self._ask_decision, include_neow=False, **kwargs)

    # ── replay recorded combat, else force-win to keep floors advancing ──
    def _run_combat(self, encounter, room_type):
        from ..combat_card_db import CombatCardDb
        from ..rewards import GOLD_REWARD_RANGES

        run = self.run
        combat = run.create_combat(encounter, room_type=room_type)
        self._combat = combat
        try:
            # If the recording's next command is a combat command, this fight
            # is annotated: replay it card-for-card against the live parity
            # combat and collect its divergences (SP3). Otherwise the fight is
            # un-annotated / unported and we fall back to the force-win stub.
            nxt = self._cursor.peek()
            if nxt is not None and nxt.name in _COMBAT_CMDS:
                db = CombatCardDb()
                db.start(combat)
                driver = ReplayCombatDriver(combat, self._cursor, db)
                self.combat_divergences.extend(driver.play())
                self.unresolved_play_card_ids.extend(driver.unresolved_play_card_ids)
                # If the replay stopped mid-fight (un-ported effect / unresolved
                # id), the cursor is parked on a combat command. Drop the fight's
                # remaining combat commands so the post-combat reward (TakeCard)
                # and the next room's decisions realign instead of the reward
                # lookahead dead-ending on the stopped command.
                self._cursor.skip_while(_COMBAT_TAIL_CMDS)
            if not combat.is_over:
                # No combat annotations, or the replay diverged/stopped before
                # the enemies died: force the win so the run keeps walking.
                self.forced_combats += 1
                for enemy in combat.enemies:
                    enemy.hp = 0
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
        if kind == DecisionKind.REWARD_CARD:
            return self._answer_reward_card(request, legal)
        if kind == DecisionKind.SHOP:
            return self._answer_shop(request, legal)
        if kind == DecisionKind.SELECT_CARDS and self._combat is None:
            # An OUT-OF-COMBAT card-grid selection (rest-site SMITH, and the
            # upgrade/transform/remove events). Follow the recording's grid
            # click so the deck evolves exactly as it did in the run — the Hand
            # annotations of every later fight depend on the right card being
            # upgraded/removed. (In-combat selections — Headbutt's
            # discard->draw pick etc. — route here too, but with `self._combat`
            # set; those stay on the default until the in-combat selection
            # stream is wired.)
            return self._answer_select_grid(request, legal)
        # Shop / other card-selection choices don't move the SP2 streams
        # (generation is choice-independent); take the first legal action,
        # which always progresses (skip a reward, leave a shop, pick a card).
        return legal[0]

    def _answer_select_grid(self, request: DecisionRequest, legal: list[int]) -> int:
        # `SelectGridCard i j k …` names the i-th, j-th, … card in the grid as
        # displayed. The game's grid is `Deck.Cards.Where(<filter>)` in deck
        # order shown with SortingOrders.Ascending, which sorts by the list's
        # own index (i.e. a no-op) — so the indices point straight into the
        # request's candidates, which the driver builds from the same
        # deck-order filtered list.
        #
        # ONE command == ONE screen: RunReplays' DeckCardSelectRecordPatch
        # collects every selected card's index into a single command
        # ("multi-card selections … recorded atomically"), and each index is
        # `selectable.IndexOf(card)` on the grid *as first shown*. The sim's
        # driver, by contrast, asks one SELECT_CARDS request per pick against a
        # candidate list that shrinks as picks are taken
        # (`RunDriver._card_selector`). So we consume the command on the first
        # ask, resolve all of its indices against that original grid, and serve
        # the picks one at a time — a later index like the 8 in Claws'
        # `SelectGridCard 0 1 2 3 8` must not be re-read against the
        # four-shorter remainder.
        #
        # No recorded SelectGridCard before the next room boundary (or a screen
        # confirmed with fewer picks than MaxSelect — Claws is MinSelect 0)
        # means: stop. Skippable screens take their skip action; the rest fall
        # back to the first legal action.
        stop = legal[-1] if request.skippable else legal[0]
        # `_grid_open` is the count_remaining the next ask of the screen we are
        # already serving will carry (None = no screen open), so a fresh screen
        # is never mistaken for a continuation and a continuation never re-scans
        # the cursor.
        if getattr(self, "_grid_open", None) != request.count_remaining:
            self._grid_picks = []
            cmd = self._cursor.take_before("SelectGridCard", _ROOM_BOUNDARY)
            if cmd is not None:
                self._grid_picks = [
                    request.candidates[int(a)] for a in cmd.args
                    if a.lstrip("-").isdigit()
                    and 0 <= int(a) < len(request.candidates)
                ]
        while self._grid_picks:
            card = self._grid_picks.pop(0)
            for i, candidate in enumerate(request.candidates):
                if candidate is card and i in legal:
                    self._grid_open = request.count_remaining - 1
                    return i
        self._grid_open = None                # screen closed — nothing left
        return stop

    def _answer_reward_card(self, request: DecisionRequest, legal: list[int]) -> int:
        # Follow the recording's card-reward pick so the deck evolves exactly
        # as it did in the run (between-fight deck state — the Hand annotations
        # of every later fight depend on it). `TakeCard N` takes the N-th
        # offered card; no TakeCard before the next room boundary means the
        # reward was skipped (RewardsSet lets the player leave a card behind).
        n = len(request.rewards.cards)
        skip = n if n in legal else legal[0]
        cmd = self._cursor.take_before("TakeCard", _ROOM_BOUNDARY)
        # `TakeCard skip` is an explicit leave-the-reward (recorded when the run
        # took no card); so is no TakeCard before the next room boundary.
        if cmd is None or not cmd.args or not cmd.args[0].lstrip("-").isdigit():
            return skip
        idx = int(cmd.args[0])
        return idx if idx in legal else skip

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

    def _answer_shop(self, request: DecisionRequest, legal: list[int]) -> int:
        # One shop-loop iteration: buy the next recorded item, else leave. The
        # shop is parity-generated on the Shops stream, so the recorded
        # BuyCard/BuyRelic/BuyPotion names resolve against the live inventory;
        # BuyCardRemoval fires the removal, whose card pick is the following
        # SelectGridCard (served out-of-combat by _answer_select_grid). Buying
        # the right cards / removing the right one is what keeps the deck (hence
        # every later fight's hand) in sync.
        entries = request.shop.all_entries
        leave = len(entries)
        # A purchase the live inventory can't offer (the shop stocked a
        # different relic — the grab-bag identities are not game-exact yet) is
        # SKIPPED, not treated as "leave": the recording's later purchases in
        # this same shop still have to land, because every later fight's hand
        # depends on the cards that entered the deck here.
        while True:
            cmd = self._cursor.take_first_of(_SHOP_CMDS, _ROOM_BOUNDARY)
            if cmd is None:
                return leave
            idx = self._shop_entry_index(request.shop, entries, cmd)
            if idx is not None and idx in legal:
                return idx

    def _shop_entry_index(self, shop, entries, cmd) -> int | None:
        from ..shop import (
            MerchantCardEntry,
            MerchantPotionEntry,
            MerchantRelicEntry,
        )
        from .combat_driver import card_display_name

        if cmd.name == "BuyCardRemoval":
            rm = shop.card_removal_entry
            return entries.index(rm) if rm in entries else None
        want = " ".join(cmd.args).strip()
        for i, e in enumerate(entries):
            if (cmd.name == "BuyCard" and isinstance(e, MerchantCardEntry)
                    and e.card is not None
                    and card_display_name(e.card) == want):
                return i
            if (cmd.name == "BuyRelic" and isinstance(e, MerchantRelicEntry)
                    and e.relic is not None and e.relic.name == want):
                return i
            if (cmd.name == "BuyPotion" and isinstance(e, MerchantPotionEntry)
                    and e.potion is not None and e.potion.name == want):
                return i
        return None

    def _answer_rest(self, request: DecisionRequest, legal: list[int]) -> int:
        # Bounded to THIS room. A rest visit can ask more than once (Miniature
        # Tent's ShouldDisableRemainingRestSiteOptions keeps it open) and the
        # recording has no explicit "Leave" — the block just ends. An unbounded
        # scan would then answer that last ask with the NEXT rest site's
        # option, silently eating every command in between (the intervening
        # rooms' MoveToMapCoord included) and desyncing the walk.
        cmd = self._cursor.take_before("ChooseRestSiteOption", _ROOM_BOUNDARY)
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

    def _node_picked_relics(self, act_index: int, room_index: int) -> list[str]:
        """The relic ids the save says were actually picked at map node
        (`act_index`, `room_index`) — relic_choices with was_picked. Each act's
        node 0 (the Ancient/Neow start node) is handled separately (_neow_relics
        / the shrine); this serves the treasure/elite/boss nodes of any act."""
        history = self.oracle.map_history
        hist = history[act_index] if act_index < len(history) else []
        if room_index >= len(hist):
            return []
        out: list[str] = []
        for stat in hist[room_index].get("player_stats", []):
            for choice in stat.get("relic_choices", []):
                if choice.get("was_picked") and choice.get("choice"):
                    out.append(relic_key(choice["choice"]))
        return out

    def _reconcile_node_relics(self, run, act_index: int, room_index: int,
                               n_before: int) -> None:
        """Make the relics granted while resolving map node (`act_index`,
        `room_index`) match the ones the save says were picked there, replacing
        the sim's RNG picks.

        The sim grants treasure/elite relics off the front of the grab bag on
        the (uncompared) TreasureRoomRelics stream, which isn't draw-order-
        faithful yet — so the grabbed relic (e.g. Strike Dummy, +3 to Strikes)
        is usually the wrong one and skews every later fight's damage. The save
        records the real pick per node (map_history relic_choices/was_picked),
        so — as with card rewards (TakeCard) and the SMITH grid (SelectGridCard)
        — follow it: drop any relic the sim auto-granted at this node that the
        save didn't pick, and add the picked ones it's missing. Only the relic
        list matters for combat parity. An unported picked relic is dropped
        without a replacement (better a missing relic than a wrong effect)."""
        picked = set(self._node_picked_relics(act_index, room_index))
        granted = list(run.relics[n_before:])
        if not picked and not granted:
            return
        for relic in granted:
            if relic.id not in picked:
                run.relics.remove(relic)
                # Un-pick it properly: a max-HP relic (Mango, Pear, …) already
                # ran its AfterObtained, and leaving that +MaxHp behind would
                # read as a player-state divergence for the rest of the run.
                relic.undo_after_obtained(run)
        owned = {r.id for r in run.relics}
        for rid in self._node_picked_relics(act_index, room_index):
            if rid not in owned and rid in _all_relic_ids():
                run.add_relic(rid)
                owned.add(rid)

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

    def _consume_ancient_map_move(self, cursor, run, divergences) -> None:
        """Eat the `MoveToMapCoord` that walks INTO a new act's Ancient node.

        Act 0 begins standing on Neow's node, but every later act drops the
        player on the map screen *above* the board, so the recording clicks the
        Ancient start node as a real move before the shrine plays:

            ProceedToNextAct / VoteForMapCoordAction / MoveToMapCoord <startCol>
            / ChooseEventOption <shrine> / MoveToMapCoord <first room>

        The save agrees — the live act's `visited_map_coords` starts at the
        ancient's `(startCol, row 0)`. `start_act` already stands the sim on
        `map.starting_point`, so this command must be consumed, not walked:
        walking it makes the act's first room land on row 1 as row 2 and shifts
        every later row by one, which desyncs the whole act's map path a few
        rooms in ("unreachable map coord")."""
        cmd = cursor.take("MoveToMapCoord")
        if cmd is None or not cmd.args:
            return
        col = int(cmd.args[0])
        start = run.current_point
        if col != start.col or start.row != 0:
            divergences.append(Divergence(
                "runner", 0, f"(col={col}, row=0)",
                f"(col={start.col}, row={start.row})",
                "act-entry Ancient node move does not match the start point",
            ))

    def _check_player_state(self, run, divergences, act_index,
                            player_checkpoints, resync_player) -> None:
        """Assert sim HP/max-HP against the completed act's floor snapshot
        (from the sibling run.save), then optionally resync so an act's bug
        can't cascade. Parity oracle only — no effect when checkpoints omit
        this act. Streams: player_hp / player_max_hp; command_index = act."""
        if not player_checkpoints or act_index not in player_checkpoints:
            return
        exp_hp, exp_max = player_checkpoints[act_index]
        if run.hp != exp_hp:
            divergences.append(Divergence(
                "player_hp", act_index, exp_hp, run.hp,
                f"act {act_index} boundary"))
        if run.max_hp != exp_max:
            divergences.append(Divergence(
                "player_max_hp", act_index, exp_max, run.max_hp,
                f"act {act_index} boundary"))
        if resync_player:
            run.hp = exp_hp
            run.max_hp = exp_max

    def run(self, stop_after_act: int = 0,
            player_checkpoints: "dict[int, tuple[int, int]] | None" = None,
            resync_player: bool = False) -> ReplayResult:
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

        # The game enters the run's Neow/start node as a real map point
        # (RunManager.EnterMapPointInternal -> AppendToMapPointHistory), so it
        # occupies MapPointHistory[act0][0] (the save records it as the Ancient
        # start node) and counts toward IRunState.TotalFloor. TotalFloor seeds
        # every per-ENCOUNTER Rng (make_encounter_rng), so a run whose start
        # node is uncounted seeds every fight's monster-selection one floor too
        # low. This runner injects that node (hist[0]) instead of walking into
        # it, and the sim models Neow as a run-start event (never an enter_point
        # that bumps total_floor), so seed it here to match the game's count.
        run.total_floor = 1

        hist = self.oracle.map_history[0] if self.oracle.map_history else []
        divergences: list[Divergence] = []
        room_index = 1  # per-act; hist[0] is that act's Ancient start node
        rooms_total = 0  # cumulative across acts (room_index resets per act)
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
            n_relics_before = len(run.relics)
            resolution = run.enter_point(dest)
            if room_index < len(hist):
                d = compare_node_type(
                    room_index, hist[room_index].get("map_point_type", ""),
                    resolution.map_point_type,
                )
                if d is not None:
                    divergences.append(d)
            driver._resolve_room(resolution)
            self._reconcile_node_relics(
                run, run.act_index, room_index, n_relics_before)
            room_index += 1
            rooms_total += 1
            if run.is_dead:
                reason = "player died"
                break
            if run.at_act_end:
                reached_act_end = True
                self._check_player_state(
                    run, divergences, run.act_index,
                    player_checkpoints, resync_player)
                if run.act_index >= stop_after_act:
                    reason = f"reached act {run.act_index} boss"
                    break
                run.advance_act()
                # Every act begins on an Ancient starting node that the game
                # records in MapPointHistory (the save shows act N's floor as an
                # `ancient` entry — e.g. act 2 floor 18), so it counts toward
                # IRunState.TotalFloor exactly like act 0's Neow node seeded
                # above (total_floor = 1). The sim fires this shrine as an
                # act-entry event (_maybe_run_ancient), never an enter_point that
                # bumps total_floor, so count it here — otherwise every act-2+
                # per-encounter Rng (make_encounter_rng seeds on TotalFloor) is
                # one floor too low and picks the wrong monster composition.
                run.total_floor += 1
                self._consume_ancient_map_move(cursor, run, divergences)
                driver._maybe_run_ancient()
                # Switch the node-type/relic oracle to the new act's history and
                # restart the per-act room index (hist[0] is that act's Ancient
                # start node, entered as room_index 1 next). Without this both
                # compare_node_type and _reconcile_node_relics stay pinned to
                # act 0 and silently no-op for every act past the first.
                hist = (self.oracle.map_history[run.act_index]
                        if run.act_index < len(self.oracle.map_history) else [])
                room_index = 1
                reached_act_end = False

        run_counters = run.rng_set.counters()
        player_counters = run.player_rng.counters()
        divergences.extend(
            compare_counters(run_counters, player_counters, self.oracle))

        # SP3: the seven combat streams are diffed as their own bucket, joined
        # by the per-command Hand/Enemies mismatches the driver collected. Kept
        # out of `divergences` so SP2 conformance stays combat-agnostic.
        combat_divergences = list(driver.combat_divergences)
        combat_divergences.extend(compare_counters(
            run_counters, player_counters, self.oracle,
            run_streams=SP3_COMBAT_STREAMS, player_streams=()))

        return ReplayResult(
            divergences=divergences,
            run_counters=run_counters,
            player_counters=player_counters,
            rooms_walked=rooms_total,
            reached_act_end=reached_act_end,
            stopped_reason=reason,
            combat_divergences=combat_divergences,
            unresolved_play_card_ids=list(driver.unresolved_play_card_ids),
            forced_combats=driver.forced_combats,
        )
