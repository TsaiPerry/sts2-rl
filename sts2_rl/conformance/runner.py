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


def _node_relic_choices(oracle: "SaveOracle", act_index: int, room_index: int) -> list[str | None]:
    """The relic ids the save says were OFFERED (not just picked) at map node
    (`act_index`, `room_index`), in the order the game asked about them —
    every `relic_choices` entry, `was_picked` or not. `None` marks an entry
    with no recorded identity (an unported/unresolvable choice).

    Mirrors `ReplayRunner._node_picked_relics`, which filters this same list
    down to `was_picked` entries to correct which relic was KEPT
    (`_reconcile_node_relics`). This unfiltered version answers a different
    question — which relic was OFFERED at the Nth ask — needed to relabel a
    `REWARD_RELIC` `DecisionRequest.relic` (the sim's own grab-bag pull,
    drawn off a stream that is not draw-order-faithful yet) with the save's
    ground truth before an obs is built from it."""
    history = oracle.map_history
    hist = history[act_index] if act_index < len(history) else []
    if room_index >= len(hist):
        return []
    out: list[str | None] = []
    for stat in hist[room_index].get("player_stats", []):
        for choice in stat.get("relic_choices", []):
            cid = choice.get("choice")
            out.append(relic_key(cid) if cid else None)
    return out


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


def crystal_sphere_click_policy(cursor: "_CommandCursor"):
    """A `RunState.crystal_sphere_clicks` policy that replays a recording's
    `CrystalSphereClick {x} {y} {tool}` commands.

    RunReplays records the minigame's spatial decision verbatim
    (RunReplays/Commands/CrystalSphereClickCommand.cs, recorded by the
    `CellClicked` prefix in Patches/CrystalSpherePatch.cs), so a replay does
    not need a policy at all — the clicks are data, and the tool is the one
    that was actually in effect at click time.

    The lookahead is bounded by `_ROOM_BOUNDARY`: without it, a minigame with
    no recorded clicks would scan forward and steal the clicks belonging to a
    later crystal sphere. Falling short, it defers to the event's own
    automated rule by returning None."""
    def policy(game):
        cmd = cursor.take_before("CrystalSphereClick", _ROOM_BOUNDARY)
        if cmd is None or len(cmd.args) < 3:
            return None
        return (int(cmd.args[0]), int(cmd.args[1]), int(cmd.args[2]))
    return policy


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
        # Ground truth for relabeling a REWARD_RELIC ask's offer (see
        # `_relabel_relic_offer`): `ReplayRunner.run()` stamps `_oracle` and
        # the current (act, room) onto this driver right before every
        # `_resolve_room` call, and `_relic_ask_counts` tracks how many
        # REWARD_RELIC asks have already been served at the current node (a
        # node can offer several relics one at a time — Calling Bell's
        # three, Toy Box's four).
        self._oracle = None
        self._cur_act_index = 0
        self._cur_room_index = 0
        self._relic_ask_counts: dict[tuple[int, int], int] = {}
        super().__init__(run, ask=self._ask_decision, include_neow=False, **kwargs)

    # ── replay recorded combat, else force-win to keep floors advancing ──
    def _run_combat(self, encounter, room_type):
        from ..rewards import GOLD_REWARD_RANGES

        run = self.run
        # `track_card_ids` starts the combat's own `NetCombatCardDb` at the
        # game's `SetUpCombat` instant, so turn-1 generated cards are id'd as
        # they are ADDED. It has to be asked for before we know whether this
        # fight is annotated (the cursor peek below), because by the time we
        # do, turn 1 has already run.
        combat = run.create_combat(encounter, room_type=room_type,
                                   track_card_ids=True)
        self._combat = combat
        try:
            # If the recording's next command is a combat command, this fight
            # is annotated: replay it card-for-card against the live parity
            # combat and collect its divergences (SP3). Otherwise the fight is
            # un-annotated / unported and we fall back to the force-win stub.
            nxt = self._cursor.peek()
            if nxt is not None and nxt.name in _COMBAT_CMDS:
                driver = ReplayCombatDriver(combat, self._cursor, combat.card_db)
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
            self._offer_rewards(run.generate_combat_rewards(
                room_type, encounter=encounter,
                # `CombatRoom.OnCombatEnded` (CombatRoom.cs:233-236) reads the
                # encounter's gold proportion off the finished combat, and
                # `RewardsSet` scales the MONSTER gold range by it. The sim
                # always passed the 1.0 default, so an encounter that lets an
                # enemy escape still paid full gold.
                gold_proportion=encounter.calculate_gold_proportion(combat),
            ))
        return combat

    # ── the decision seam for everything resolved inside a room ──────────
    def _ask_decision(self, request: DecisionRequest) -> int:
        self.prepare_request(request)
        return self._answer(request)

    def prepare_request(self, request: DecisionRequest) -> None:
        """Ground-truth corrections applied to `request` BEFORE anything else
        looks at it — in particular before `sim_obs_dump._ObsSink.record`
        builds an obs from it, since `_DumpingForceWinDriver._ask_decision`
        records the request itself, not this class's `_ask_decision` (which
        it overrides). Split out of `_ask_decision` for exactly that reason:
        the dumping subclass needs to run this step before its own recording
        hook, then answer via `_answer` directly rather than through
        `_ask_decision` again (which would run this step a second time and
        double-advance `_relic_ask_counts`)."""
        if request.kind == DecisionKind.REWARD_RELIC:
            # `request.relic` is the sim's own (not draw-order-faithful)
            # grab-bag pull at this point, so it disagrees with the game's
            # actual offer just like the granted relic used to before
            # `_reconcile_node_relics` existed. Relabel it here, from the
            # same save ground truth, BEFORE any obs gets built from this
            # request (`_relabel_relic_offer`) — the object identity is all
            # that changes; `_answer` below still always takes.
            self._relabel_relic_offer(request)

    def _answer(self, request: DecisionRequest) -> int:
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
        if kind == DecisionKind.REWARD_RELIC:
            # RelicReward is take-or-skip in the game and now in the sim too
            # (RunState.offer_relic), but the recording does not carry a
            # per-offer command: the pick is in the SAVE, as the node's
            # relic_choices/was_picked entries. Keep taking (legal[0] == 0)
            # and let `_reconcile_node_relics` correct the node afterwards —
            # it already has to, because the sim's grab-bag identities are not
            # draw-order-faithful yet, so answering the offer from the save
            # here would fix only which relics were KEPT, not which were
            # OFFERED.
            return 0
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

    def _relabel_relic_offer(self, request: DecisionRequest) -> None:
        """Replace `request.relic` — the sim's own (not draw-order-faithful)
        grab-bag pull — with the save's ground truth for the Nth REWARD_RELIC
        ask at the current node, so an obs built from this request (before
        the take/skip decision) shows what the game actually offered instead
        of the sim's mispull. A no-op with no oracle attached (e.g. a bare
        unit-test driver) or once the current node's recorded offers run out
        (an offer the save doesn't cover, or an unresolvable/unported id) —
        `request.relic` is left as the sim's pull in those cases, same as
        before this method existed."""
        if self._oracle is None:
            return
        node = (self._cur_act_index, self._cur_room_index)
        idx = self._relic_ask_counts.get(node, 0)
        self._relic_ask_counts[node] = idx + 1
        choices = _node_relic_choices(self._oracle, *node)
        if idx >= len(choices):
            return
        rid = choices[idx]
        if rid is None or rid not in _all_relic_ids():
            return
        if request.relic is not None and request.relic.id == rid:
            return
        from ..relics import make_relic
        request.relic = make_relic(rid)

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
                               n_before: int,
                               bag_before: list[str] | None = None) -> None:
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
                # The swap must ALSO undo the sim's grab-bag pull: the game
                # never removed this id from its bag (it pulled `picked`
                # instead), so leave it available for later pulls — put it
                # back at its pre-room position (89U's floor-8 chest granted
                # the sim's own front pull, the reconcile swapped the RELIC
                # LIST to the save's Vajra, and the untouched bag then let
                # the floor-9 shop re-offer Vajra — a relic the player
                # already owned — where the game stocked Pendulum).
                if (bag_before is not None
                        and relic.id not in run.relic_grab_bag
                        and relic.id in bag_before):
                    pos = bag_before.index(relic.id)
                    run.relic_grab_bag.insert(
                        min(pos, len(run.relic_grab_bag)), relic.id)
        owned = {r.id for r in run.relics}
        for rid in self._node_picked_relics(act_index, room_index):
            if rid not in owned and rid in _all_relic_ids():
                run.add_relic(rid)
                owned.add(rid)
            # Mirror the game's pull for the relic it actually granted here:
            # it is owned now, so it must leave the sim's bag too (add_relic
            # deliberately never touches the bag — only pulls do).
            if rid in run.relic_grab_bag:
                run.relic_grab_bag.remove(rid)

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

    def _use_map_potion(self, run, cmd, divergences, room_index) -> None:
        """Drink one out-of-combat `UsePotion` through RunState.use_potion.

        `UsePotion N` names a real belt SLOT, but resolve by the recorded
        identity comment (`# POTION.FRUIT_JUICE`) exactly as the combat driver
        does — the sim can legitimately hold a different potion in that slot
        while the potion-retention divergence is open, and drinking the wrong
        one would be worse than reporting."""
        from .combat_driver import ReplayCombatDriver

        slot = int(cmd.args[0]) if cmd.args and cmd.args[0].lstrip("-").isdigit() else -1
        live = {i: p.id for i, p in enumerate(run.potions) if p is not None}
        want = ReplayCombatDriver._recorded_potion_id(cmd)
        if want is not None:
            if want not in live.values():
                divergences.append(Divergence(
                    "potion", room_index, want, list(live.values()),
                    f"recorded map potion (belt slot {slot}) not held",
                ))
                return
            if live.get(slot) != want:
                slot = next(i for i, pid in live.items() if pid == want)
        if not run.use_potion(slot):
            divergences.append(Divergence(
                "potion", room_index, live.get(slot), None,
                f"map UsePotion on belt slot {slot} was refused "
                "(empty slot, or the potion is not PotionUsage.AnyTime)",
            ))

    def _check_room_stats(self, run, divergences, act_index, room_in_act) -> None:
        """DETECTOR 5: diff sim player state against this room's
        map_point_history player_stats (run-END capture). Report-only —
        never resyncs, never raises. Streams: room_hp / room_max_hp /
        room_gold; command_index = run.total_floor so triage can sort by
        floor.

        Alignment (resolved empirically against 933T act 0, known HP series
        [80, 76, 74, 74, 80, 71, ...]): `room_stats_by_act[act][room_in_act]`
        lines up 1:1 with the caller's `room_index` — index 0 is the
        act-entry Ancient node, matching `map_history`/`hist[room_index]`
        used by `compare_node_type`/`_reconcile_node_relics` at the same call
        site. No offset needed."""
        acts = self.oracle.room_stats_by_act
        if act_index >= len(acts) or room_in_act >= len(acts[act_index]):
            return
        st = acts[act_index][room_in_act]
        # Terminal-point capture guard (Task 3 / oracle_semantics_probe
        # decision table): the run's LAST resolved point (the final act's
        # boss room) captures an all-zero `player_stats` block
        # (current_hp/max_hp/current_gold all 0) in every installed
        # recording — a run-end capture artifact (the point is written
        # before/around the boss kill rather than after it resolves), not a
        # real 0-HP/0-gold moment; the sim and the save's own top-level
        # `players[0]` block both show the player alive there. Detect it the
        # same way the decision table specifies generally — the point's
        # stats must be internally reachable from the previous point via
        # `current_hp + damage_taken - hp_healed` — and skip reporting
        # (report-only detector; nothing to resync) rather than emit a
        # phantom room_hp/room_max_hp/room_gold divergence every run.
        if st.current_hp == 0 and st.max_hp == 0 and st.current_gold == 0:
            return
        prev = (acts[act_index][room_in_act - 1] if room_in_act > 0
                else (acts[act_index - 1][-1] if act_index > 0
                      and acts[act_index - 1] else None))
        # Skip ONLY when the point is unreachable from `prev` AND the live
        # sim's hp matches `prev.current_hp` (history is provably the liar).
        # If the sim also disagrees with `prev`, fall through and record —
        # a flagged mismatch beats a silent skip.
        if (prev is not None
                and st.current_hp + st.damage_taken - st.hp_healed
                != prev.current_hp
                and run.hp == prev.current_hp):
            return
        note = f"act {act_index} room {room_in_act} ({st.map_point_type})"
        for stream, exp, got in (("room_hp", st.current_hp, run.hp),
                                 ("room_max_hp", st.max_hp, run.max_hp),
                                 ("room_gold", st.current_gold, run.gold)):
            if exp != got:
                divergences.append(
                    Divergence(stream, run.total_floor, exp, got, detail=note))

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

    def _is_stale_floor_save(self, floor: int, floor_saves) -> bool:
        """Detect a `run.save` that RunReplays did not re-export after this
        floor's room resolved (it is a byte-level-near-duplicate of the
        PREVIOUS floor's export, just with fresh `save_time`/`start_time`/
        `run_time` timestamps — everything else, including all 15 rng
        counters, is unchanged).

        Measured on the 933T39V18D recording (49 floors, 48 consecutive
        pairs): 3 pairs are exact duplicates of every compared field
        (gold/hp/deck/relics/potions/all 15 rng counters) — floor_1->floor_2,
        floor_4->floor_5, floor_47->floor_48. floor_4->floor_5 is the
        reviewer-confirmed case (the `Fasten` bought in room 4's shop is
        missing from both saves; it only appears in floor_6). Comparing full
        JSON confirmed the *only* bytes that differ between a stale pair are
        the three timestamp fields — the export genuinely re-ran, it just
        captured state from before this floor's room resolved.

        The cheapest reliable signal for this — cheaper than diffing every
        compared field, and robust even when nothing observable happened to
        the compared player state — is `visited_coords`: it is the save's
        record of map nodes entered THIS act, so a real per-room export must
        grow it by exactly 1. A stale export leaves it unchanged from the
        previous floor. Cross-checked against every floor of the 933T
        recording: `visited_coords` is +1 on every one of the other 45
        transitions and +0 on exactly the 3 stale ones above; it resets to 1
        exactly at the two act boundaries (floor_18, floor_34), which
        `current_act_index` distinguishes from a same-act staleness (a reset
        is a legitimate act-entry Ancient-node move, not a duplicate)."""
        oracle = floor_saves.get(floor)
        prev = floor_saves.get(floor - 1)
        if oracle is None or prev is None:
            return False
        return (oracle.current_act_index == prev.current_act_index
                and len(oracle.visited_coords) == len(prev.visited_coords))

    def _flat_room_stats(self) -> "dict[int, object]":
        """Flatten `self.oracle.room_stats_by_act` (per-act rows, run-END
        capture) to absolute-floor -> `RoomStats`, same walk order as
        `tools/oracle_semantics_probe.py`'s `flat` dict (floor 1 = the
        act-0 Ancient/Neow node, matching `total_floor`)."""
        flat = {}
        floor = 1
        for act_row in self.oracle.room_stats_by_act:
            for st in act_row:
                flat[floor] = st
                floor += 1
        return flat

    def _is_inconsistent_floor_save(self, floor: int, oracle, run) -> bool:
        """Detect a per-floor backup save whose `player_current_hp` matches
        NONE of the run-end save's room_stats_by_act references for this
        floor: not this room's post-resolve hp, not the previous room's exit
        hp (the dominant ENTRY-capture alignment `_check_floor_state`'s
        backups otherwise follow — see the probe table below), and not the
        arithmetic-derived entry hp (`cur.current_hp + damage_taken -
        hp_healed`, which independently reproduces the previous room's exit
        hp when history itself is self-consistent) — AND ONLY when the LIVE
        SIM (`run.hp`) agrees with one of those same references.

        Code review (2026-08-04, Critical): the first version of this method
        used ONLY oracle-internal evidence (backup vs history/arithmetic) and
        never consulted the live sim, so it could silently swallow a REAL
        divergence on any future floor whose backup happened to be
        self-inconsistent for an unrelated reason. Per the decision table,
        exclusion requires BOTH halves: the backup must be unreachable from
        the history references, AND the sim must independently agree with
        the one reachable (history/arithmetic-consistent) reference — i.e.
        the sim, not just the backup, must corroborate that the backup is
        the outlier. If the backup is inconsistent but the sim ALSO
        disagrees with history, this method returns False and
        `_check_floor_state` records the diff normally — a flagged
        divergence to investigate beats a silent skip.

        Discovered via `tools/oracle_semantics_probe.py` on the 933T39V18D
        recording (Task 3): of 49 per-floor backups, 46 line up exactly with
        one of the three references above (dominantly ENTRY(prev)). Floor 47
        is the sole live exception —

            47 | backup hp 74 | hist[47] hp 80 | hist[46] hp 66 | arith 66 | NONE

        — matching neither the post value (80) nor the entry value (66,
        corroborated twice: directly from hist[46] and via arithmetic from
        hist[47]'s own damage_taken/hp_healed). Floor 48's backup is a byte
        duplicate of 47's (`_is_stale_floor_save` already catches it via the
        unchanged `visited_coords`). Floor 49 is the final checkpointed
        floor, handled separately by `_check_floor_state`'s final-floor
        skip rule. The live sim's own room-12 hp (66, i.e. `run.hp` at this
        checkpoint) agrees with the history-derived entry value, so 74 is a
        mid-room / wrong-moment capture artifact in the backup, not ground
        truth — the floor is skipped exactly like a stale save (diff AND
        resync both suppressed; safe because the next non-excluded
        checkpoint re-compares full state, not a delta)."""
        flat = self._flat_room_stats()
        cur = flat.get(floor)
        if cur is None:
            return False
        prev = flat.get(floor - 1)
        candidates = {cur.current_hp}
        if prev is not None:
            candidates.add(prev.current_hp)
        candidates.add(cur.current_hp + cur.damage_taken - cur.hp_healed)
        backup_consistent = oracle.player_current_hp in candidates
        sim_consistent = run.hp in candidates
        return (not backup_consistent) and sim_consistent

    def _check_floor_state(self, run, divergences, floor_saves,
                           resync_floors) -> None:
        """Diff (and optionally resync) the FULL player state + all 15 stream
        counters against this floor's run.save. Report-only for anything
        unmapped — conformance reports, never raises.

        Checkpoint offset: `run.total_floor` counts rooms entered (Neow's node
        seeds it to 1; `enter_point` bumps it once per room), but the
        RunReplays `floor_N` save directories are numbered one higher — e.g.
        the room that lands `total_floor` at 17 (Thrash reward) is recorded as
        `floor_18`, and that is also the pre-existing act-boundary checkpoint
        used elsewhere in this file. Verified empirically against the 933T
        seed (Task 3 Step 3): every TakeCard-driven deck change matches
        `floor_N == total_floor + 1` exactly across acts 0-2 (battle_trance
        floor_3, molten_fist floor_4, inferno floor_6, thrash floor_18,
        dark_embrace floor_34, ...). A same-room shop purchase (BuyCard) does
        NOT reliably show up until the following floor's save in this
        recording — so the checkpoint intentionally does not attempt to
        calibrate against shop-driven deck changes.

        Stale-save guard (Critical fix, post-review): a `floor_saves` entry
        that `_is_stale_floor_save` flags is skipped entirely — no diff is
        recorded and no resync happens for this floor — exactly as if this
        floor had no oracle at all. This is safe (not a hole): whatever a
        stale floor's export missed (e.g. a shop-bought card) is *still
        present in the live sim state*, so it is still checked at the next
        NON-stale floor, which compares the FULL state again (not a delta) —
        that next checkpoint is where a real divergence introduced during the
        skipped floor would surface. Without this guard, resync treated the
        stale (pre-room) oracle as ground truth and rolled back correct live
        state one floor early, which is what fabricated the phantom
        divergences/forced-combats this fix resolves."""
        from ..rng import PlayerRngType, RunRngType
        from . import idmap
        from .comparators import Divergence

        floor = run.total_floor + 1
        oracle = floor_saves.get(floor)
        if oracle is None or self._is_stale_floor_save(floor, floor_saves):
            return
        if self._is_inconsistent_floor_save(floor, oracle, run):
            return
        if floor == max(floor_saves):
            # Final checkpointed floor: its backup is a room-ENTRY capture,
            # structurally different from the run-END oracle DETECTORS 2/3
            # check — comparing them here can never converge. Skip both the
            # diff and the resync; the final room's post-state is already
            # covered by DETECTORS 2/3 against the true run-END oracle.
            return

        def diff(stream, expected, actual, note=""):
            if expected != actual:
                divergences.append(
                    Divergence(stream, floor, expected, actual, note))
                return True
            return False

        diff("floor_hp", oracle.player_current_hp, run.hp)
        diff("floor_max_hp", oracle.player_max_hp, run.max_hp)
        diff("floor_gold", oracle.gold, run.gold)

        exp_deck = [(idmap.sim_card_id(cid), up) for cid, up in oracle.deck]
        live_deck = [(c.id, c.upgrade_level) for c in run.deck]
        deck_changed = diff("floor_deck", exp_deck, live_deck,
             "ordered (save order == game deck order); None = unported id")

        exp_relics = [idmap.sim_relic_id(r) for r in oracle.relic_ids]
        diff("floor_relics", exp_relics, [r.id for r in run.relics])

        exp_potions = {s: idmap.sim_potion_id(p)
                       for s, p in oracle.potion_slots.items()}
        # run.potions is a fixed-length list[Potion | None] (Player.cs
        # `_potionSlots`) so the enumerate index IS the real belt slot; skip
        # the empty ones the same way oracle.potion_slots omits them.
        live_potions = {i: p.id for i, p in enumerate(run.potions) if p is not None}
        potions_changed = diff("floor_potions", exp_potions, live_potions)

        live_rc = run.rng_set.counters()
        for t in RunRngType:
            diff(f"floor_counter_{t.value}", oracle.run_counters[t], live_rc[t])
        live_pc = run.player_rng.counters()
        for t in PlayerRngType:
            diff(f"floor_counter_{t.value}",
                 oracle.player_counters[t], live_pc[t])

        if not resync_floors:
            return
        run.hp = oracle.player_current_hp
        run.max_hp = oracle.player_max_hp
        run.gold = oracle.gold
        run.rng_set.load_counters(oracle.run_counters)
        run.player_rng.load_counters(oracle.player_counters)
        # Rebuild deck/potions only when the diff above found a mismatch:
        # unconditional rebuild on every floor forced_combats 1->7 (measured
        # on 933T) by churning fresh object identities even when unchanged.
        # Relics don't need this guard — `_resync_relics` only touches the delta.
        if deck_changed:
            self._resync_deck(run, oracle)
        self._resync_relics(run, oracle)
        if potions_changed:
            self._resync_potions(run, oracle)

    def _resync_deck(self, run, oracle) -> None:
        """Rebuild run.deck to the save's ordered contents. Unmapped ids are
        skipped (reported by the floor_deck diff). Upgrades applied by level."""
        from . import idmap
        from ..cards import make_card

        new_deck = []
        for cid, up in oracle.deck:
            sim_id = idmap.sim_card_id(cid)
            if sim_id is None:
                continue
            card = make_card(sim_id)
            for _ in range(up):
                card.upgrade()
            new_deck.append(card)
        run.deck[:] = new_deck

    def _resync_relics(self, run, oracle) -> None:
        """Reconcile run.relics to the save's list, reusing the node-relic
        pattern (undo_after_obtained on drops so max-HP side effects unwind —
        harmless here because hp/max_hp are re-pinned right before this)."""
        from . import idmap

        want = [idmap.sim_relic_id(r) for r in oracle.relic_ids]
        want_set = {w for w in want if w is not None}
        for relic in list(run.relics):
            if relic.id not in want_set:
                run.relics.remove(relic)
                relic.undo_after_obtained(run)
        owned = {r.id for r in run.relics}
        for rid in want:
            if rid is not None and rid not in owned:
                run.add_relic(rid)
                owned.add(rid)
        run.hp = oracle.player_current_hp      # re-pin after relic hooks
        run.max_hp = oracle.player_max_hp

    def _resync_potions(self, run, oracle) -> None:
        """Rebuild run.potions to the save's real slot layout (slot_index ->
        id), preserving empty slots. Player.cs's belt is a fixed-length
        `List<PotionModel?>` and LoadPotions places each potion at its
        serialized SlotIndex (see RunState.potions) — a dense rebuild would
        collapse the gaps right back and immediately re-trip the
        floor_potions diff on the very next checkpoint. Unmapped ids
        (reported by the floor_potions diff) and slots beyond max_potions are
        left/dropped empty."""
        from . import idmap
        from ..potion_pools import make_pool_potion

        new_potions: list = [None] * run.max_potions
        for slot, pid in oracle.potion_slots.items():
            if slot >= run.max_potions:
                continue
            sim_id = idmap.sim_potion_id(pid)
            if sim_id is not None:
                # make_pool_potion (not potions.make_potion): a pooled but
                # unimplemented id (e.g. mazaleths_gift) resyncs into a
                # _ParityPotion placeholder rather than KeyError-ing.
                new_potions[slot] = make_pool_potion(sim_id)
        run.potions[:] = new_potions

    def _recorded_unlock_state(self):
        """The recording's own `UnlockState`, for
        `ActModel.ApplyDiscoveryOrderModifications`.

        The pass overrides an act's rolled boss with the first entry of
        `BossDiscoveryOrder` the PROFILE has not seen (RunManager.cs:678-684),
        and its gate is true for every ordinary Standard run — so replaying a
        recording on the wrong profile can fight the wrong boss. The save
        carries the real one under `players[0].unlock_state`; sim encounter
        keys are matched to the recorded `ENCOUNTER.*` ids through the same
        map the pool oracle uses.
        """
        from ..rooms import UnlockState
        from .ids import ENCOUNTER_GAME_IDS

        seen = set(self.oracle.encounters_seen)
        keys = frozenset(k for k, gid in ENCOUNTER_GAME_IDS.items()
                         if gid in seen)
        return UnlockState(encounters_seen=keys,
                           number_of_runs=self.oracle.number_of_runs)

    def run(self, stop_after_act: int = 0,
            player_checkpoints: "dict[int, tuple[int, int]] | None" = None,
            resync_player: bool = False,
            floor_saves: "dict[int, SaveOracle] | None" = None,
            resync_floors: bool = False,
            check_room_stats: bool = False) -> ReplayResult:
        """Drive the recording through act index `stop_after_act` (inclusive)
        and report divergences + the live SP2 stream counters."""
        from ..run import RunState

        rec = self.recording
        acts = [short_act_name(a) for a in rec.acts]
        run = RunState(string_seed=rec.seed,
                       unlock_state=self._recorded_unlock_state())
        # Determinism, not parity: the legacy shared rng (SP4 debt) is seeded
        # so repeated triage runs are bit-identical and a post-fix delta is
        # attributable to the fix ([[conformance-replay-determinism]] is now
        # obsolete for conformance runs). Any in-combat draw from it is still
        # a wrong-stream bug (DETECTOR 1 / Task 5's tripwire gate).
        run.rng.seed(f"conformance:{rec.seed}")
        cursor = _CommandCursor(rec.commands)
        # The Crystal Sphere minigame's cell clicks are recorded, so replay
        # them instead of inventing them (see crystal_sphere_click_policy).
        run.crystal_sphere_clicks = crystal_sphere_click_policy(cursor)
        driver = _ForceWinDriver(run, cursor, acts=acts, ascension=rec.ascension)
        driver._oracle = self.oracle

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
            # `UsePotion` between two rooms is an AnyTime potion drunk on the
            # MAP (PotionUsage.AnyTime — Blood Potion, Entropic Brew, Foul
            # Potion, Fruit Juice). Every in-combat one has already been
            # consumed by ReplayCombatDriver or dropped with a stopped fight's
            # tail, so anything still here belongs to the walk. Left
            # unconsumed it was silently skipped, and the belt and the asserted
            # HP drifted from the recording for the rest of the run.
            cmd = cursor.take("MoveToMapCoord", "UsePotion")
            while cmd is not None and cmd.name == "UsePotion":
                self._use_map_potion(run, cmd, divergences, room_index)
                cmd = cursor.take("MoveToMapCoord", "UsePotion")
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
            relic_bag_before = list(run.relic_grab_bag)
            resolution = run.enter_point(dest)
            if room_index < len(hist):
                d = compare_node_type(
                    room_index, hist[room_index].get("map_point_type", ""),
                    resolution.map_point_type,
                )
                if d is not None:
                    divergences.append(d)
            # Stamp the node any REWARD_RELIC ask resolved during this room
            # belongs to, so `_relabel_relic_offer` can look up the save's
            # per-offer ground truth (`_reconcile_node_relics` below is keyed
            # the same way, off `run.act_index`/`room_index`).
            driver._cur_act_index = run.act_index
            driver._cur_room_index = room_index
            driver._resolve_room(resolution)
            self._reconcile_node_relics(
                run, run.act_index, room_index, n_relics_before,
                bag_before=relic_bag_before)
            if floor_saves:
                self._check_floor_state(
                    run, divergences, floor_saves, resync_floors)
            if check_room_stats:
                self._check_room_stats(
                    run, divergences, run.act_index, room_index)
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
