"""SP2 Task 10: the conformance runner replays a recording through the
parity-sim with a force-win combat stub and diffs the walk + RNG counters.

Task 9 wired the four SP2 RNG streams onto the parity RNG:
  - ``UpFront`` — run/room generation (8f), 413 at the act-1 boss.
  - ``UnknownMapPoint`` — "?"-node resolution (RunOddsSet), 3.
  - ``Rewards`` — combat/treasure reward generation (gold, potion pity+drop,
    cards, elite relic rarity), 141.
  - ``Shops`` — merchant generation (on-sale index, card/potion picks, cost
    jitter), 56. (Merchant card/relic rarity + upgrade rolls draw on the
    *Rewards* stream, as in the source.)

The full act-1 walk of 89U21BV1TZ (Ironclad) reproduces all four counters
exactly with zero divergences.

Cross-seed note: ``Shops`` / ``UnknownMapPoint`` / ``UpFront`` match all five
RunReplays recordings; ``Rewards`` matches every seed whose act-1 events award
nothing on the reward stream. Two seeds (DJDCSAQZNR, QRWCVDPZN5) walk through
events (brain_leech, self_help_book, …) whose per-event reward-draw counts the
Ironclad-only sim doesn't yet reproduce — an event-fidelity gap distinct from
the reward/shop wiring, tracked separately."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.rng import PlayerRngType, RunRngType

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

SEED = "89U21BV1TZ"  # floor_18 = act 1 only (no Hive act-2 map divergence)

# Every SP2 stream + its expected floor-18 counter for the Ironclad seed.
_EXPECTED_RUN = {RunRngType.UP_FRONT: 413, RunRngType.UNKNOWN_MAP_POINT: 3}
_EXPECTED_PLAYER = {PlayerRngType.REWARDS: 141, PlayerRngType.SHOPS: 56}


def _run(seed: str, floor: str = "floor_18"):
    base = REC / seed / floor
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    return ReplayRunner(rec, oracle).run(stop_after_act=0), oracle


def test_runner_reproduces_act1_walk():
    result, oracle = _run(SEED)
    # Every MoveToMapCoord landed on a travelable node of the recorded type,
    # all the way to the act-1 boss — no map or navigation divergence.
    assert result.reached_act_end, result.stopped_reason
    assert result.rooms_walked == len(oracle.map_history[0]) - 1  # minus Neow
    map_or_nav = [d for d in result.divergences
                  if d.stream in ("map_point_type", "runner")]
    assert not map_or_nav, map_or_nav


def test_runner_matches_run_counters():
    result, oracle = _run(SEED)
    # UpFront (room generation) and UnknownMapPoint ("?"-node resolution) both
    # land at the save value with no in-run divergence.
    for stream, expected in _EXPECTED_RUN.items():
        assert result.run_counters[stream] == oracle.run_counters[stream] == expected


def test_runner_matches_economy_counters():
    result, oracle = _run(SEED)
    # Rewards (combat/treasure reward generation) and Shops (merchant
    # generation) reproduce the save counters exactly.
    for stream, expected in _EXPECTED_PLAYER.items():
        assert result.player_counters[stream] == \
            oracle.player_counters[stream] == expected


def test_runner_has_no_divergences():
    result, _ = _run(SEED)
    # All four SP2 streams + the whole map/room-type walk agree with the save.
    assert result.ok, [str(d) for d in result.divergences]


def test_runner_combat_is_driven_not_forced_and_ids_resolve():
    # SP3 Task 8: the runner now drives annotated fights through
    # ReplayCombatDriver rather than force-winning them. Wiring the driver in
    # must not regress the SP2 subsystem (map/economy `ok` still holds), every
    # recorded PlayCard id must resolve (unresolved list empty), and the combat
    # subsystem is diffed into its OWN bucket -- so a still-un-ported later
    # fight surfaces in `combat_divergences` (Task 9's worklist) without
    # touching the SP2 `divergences`/`ok`.
    result, _ = _run(SEED)
    assert result.ok, [str(d) for d in result.divergences]
    assert result.unresolved_play_card_ids == [], result.unresolved_play_card_ids
    # Not every fight is force-won any more: the driver replayed at least one.
    assert result.forced_combats < result.rooms_walked


def test_shop_skips_an_unstockable_purchase_instead_of_leaving():
    """A recorded purchase the live inventory can't offer (the shop stocked a
    different relic — grab-bag identities are not game-exact yet) must be
    skipped, not read as "leave the shop": 933T39V18D's act-1 shop buys
    Catastrophe+, Alchemize+, Parrying Shield, Brimstone, Shrug It Off+, and
    bailing on the missing Brimstone dropped Shrug It Off+ from the deck,
    desyncing every later fight's hand."""
    from sts2_rl.conformance.runner import _CommandCursor, _ForceWinDriver
    from sts2_rl.driver import DecisionKind
    from sts2_rl.conformance.recording import Command

    def cmd(name, *args):
        return Command(name=name, args=list(args), comment="", annotation=None,
                       lineno=0)

    from sts2_rl.relics import make_relic
    from sts2_rl.shop import MerchantRelicEntry

    def entry(relic_id):
        e = MerchantRelicEntry.__new__(MerchantRelicEntry)
        e.relic = make_relic(relic_id)
        return e

    class _Shop:
        card_removal_entry = None

        def __init__(self):
            self.all_entries = [entry("parrying_shield"), entry("orrery")]

    shop = _Shop()

    class _Req:
        kind = DecisionKind.SHOP

        def __init__(self):
            self.shop = shop

        def legal_actions(self):
            return [0, 1, 2]

    cursor = _CommandCursor([
        cmd("BuyRelic", "Brimstone"),          # not stocked here — skip it
        cmd("BuyRelic", "Parrying Shield"),    # …and still buy this one
        cmd("MoveToMapCoord", "2"),
    ])
    driver = _ForceWinDriver.__new__(_ForceWinDriver)
    driver._cursor = cursor
    req = _Req()
    assert driver._answer_shop(req, req.legal_actions()) == 0
    # Nothing else to buy in this room: leave, next room's move intact.
    assert driver._answer_shop(req, req.legal_actions()) == 2
    nxt = cursor.peek()
    assert nxt is not None and nxt.name == "MoveToMapCoord"


def test_rest_site_lookahead_cannot_steal_the_next_rooms_move():
    """A Miniature Tent rest site keeps offering options until the player
    Leaves, but the recording writes no "Leave" command — the block simply
    ends. The driver's extra ask must therefore find *nothing*: an unbounded
    scan would run past the room and consume the NEXT rest site's option,
    swallowing every command in between (933T39V18D act 1: the elite's
    `MoveToMapCoord 3` vanished and the act desynced into "unreachable map
    coord" four rooms later)."""
    from sts2_rl.conformance.runner import _CommandCursor, _ForceWinDriver
    from sts2_rl.driver import REST_HEAL, REST_LEAVE, REST_SMITH, DecisionKind
    from sts2_rl.conformance.recording import Command

    def cmd(name, *args):
        return Command(name=name, args=list(args), comment="", annotation=None,
                       lineno=0)

    cursor = _CommandCursor([
        cmd("ChooseRestSiteOption", "SMITH"),
        cmd("ChooseRestSiteOption", "HEAL"),
        cmd("MoveToMapCoord", "3"),              # the next room — must survive
        cmd("ChooseRestSiteOption", "SMITH"),    # a LATER rest site
    ])

    class _Req:
        kind = DecisionKind.REST

        def legal_actions(self):
            return [REST_HEAL, REST_SMITH, REST_LEAVE]

    driver = _ForceWinDriver.__new__(_ForceWinDriver)
    driver._cursor = cursor
    req = _Req()
    assert driver._answer_rest(req, req.legal_actions()) == REST_SMITH
    assert driver._answer_rest(req, req.legal_actions()) == REST_HEAL
    # Third ask (Miniature Tent keeps the visit open): nothing left in THIS
    # room, so leave — and the next room's move is still on the cursor.
    assert driver._answer_rest(req, req.legal_actions()) == REST_LEAVE
    nxt = cursor.peek()
    assert nxt is not None and nxt.name == "MoveToMapCoord" and nxt.args == ["3"]


def test_multi_index_select_grid_is_one_screen_over_the_original_grid():
    """`SelectGridCard i j k …` is ONE screen recorded atomically: RunReplays'
    DeckCardSelectRecordPatch collects every selected card's index into a
    single command, and each index is a position in the grid *as first shown*
    (`selectable.IndexOf(card)` on the unchanged list).

    The sim's driver asks one SELECT_CARDS request per pick against a
    *shrinking* candidate list (`RunDriver._card_selector` pops each pick), so
    the runner must consume the command once, resolve every index against the
    original grid, and then serve the picks one at a time. Reading only
    `args[0]` (and re-scanning for a further `SelectGridCard` that never
    exists) makes picks 2..N fall back to `legal[0]` — which is what left
    933T39V18D's act-2 deck wrong from the Claws transform onward
    (`SelectGridCard 0 1 2 3 8`, floor_49 line 439)."""
    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import _CommandCursor, _ForceWinDriver
    from sts2_rl.driver import DecisionKind

    def cmd(name, *args):
        return Command(name=name, args=list(args), comment="", annotation=None,
                       lineno=0)

    grid = [f"c{i}" for i in range(10)]

    class _Req:
        kind = DecisionKind.SELECT_CARDS
        skippable = True

        def __init__(self, candidates, count_remaining):
            self.candidates = candidates
            self.count_remaining = count_remaining

        def legal_actions(self):
            return list(range(len(self.candidates) + 1))  # + skip

    cursor = _CommandCursor([
        cmd("SelectGridCard", "0", "1", "2", "3", "8"),
        cmd("ChooseEventOption", "-1"),
        cmd("MoveToMapCoord", "1"),
    ])
    driver = _ForceWinDriver.__new__(_ForceWinDriver)
    driver._cursor = cursor

    remaining, picked, want = list(grid), [], 6
    for i in range(want):
        req = _Req(list(remaining), want - i)
        idx = driver._answer_select_grid(req, req.legal_actions())
        if idx == len(remaining):               # the screen was confirmed early
            break
        picked.append(remaining.pop(idx))
    # Exactly the five recorded cards, in the recorded order — index 8 is the
    # ORIGINAL grid position, not a position in the four-shorter remainder.
    assert picked == ["c0", "c1", "c2", "c3", "c8"]
    # MaxSelect was 6 but the player confirmed 5 (Claws' screen is MinSelect 0),
    # so the sixth ask must stop, not steal the next room's command.
    nxt = cursor.peek()
    assert nxt is not None and nxt.name == "ChooseEventOption"


def test_map_use_potion_is_drunk_instead_of_skipped():
    """`PotionUsage.AnyTime` potions can be drunk on the MAP, and the recording
    writes a plain `UsePotion` for it between two `MoveToMapCoord`s. The runner
    used to scan straight past it — the belt and the asserted HP then drifted
    from the recording for the rest of the run."""
    import random

    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.potions import make_potion
    from sts2_rl.run import RunState

    runner = ReplayRunner.__new__(ReplayRunner)
    run = RunState(rng=random.Random(0))
    run.potions = [make_potion("fruit_juice"), make_potion("fire_potion")]
    before_max = run.max_hp
    divergences: list = []
    runner._use_map_potion(
        run,
        Command(name="UsePotion", args=["0"],
                comment="# POTION.FRUIT_JUICE", annotation=None, lineno=7),
        divergences, 3,
    )
    assert divergences == []
    assert run.potions[0] is None            # RemoveBeforeUse nulls the slot
    assert run.max_hp == before_max + 5      # FruitJuice.cs GainMaxHp(5)


def test_map_use_potion_resolves_by_identity_not_slot():
    """The recorded slot is trusted only when it holds the recorded potion —
    the same robustness the combat driver applies, because the sim can hold a
    different potion in that slot while potion retention is still diverging."""
    import random

    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.potions import make_potion
    from sts2_rl.run import RunState

    runner = ReplayRunner.__new__(ReplayRunner)
    run = RunState(rng=random.Random(0))
    run.potions = [make_potion("fire_potion"), make_potion("fruit_juice")]
    divergences: list = []
    runner._use_map_potion(
        run,
        Command(name="UsePotion", args=["0"],
                comment="# POTION.FRUIT_JUICE", annotation=None, lineno=7),
        divergences, 3,
    )
    assert divergences == []
    assert run.potions[1] is None            # slot 1, not the recorded 0
    assert run.potions[0] is not None

    # ...and a potion the sim simply is not holding is REPORTED, not guessed.
    runner._use_map_potion(
        run,
        Command(name="UsePotion", args=["0"],
                comment="# POTION.BLOOD_POTION", annotation=None, lineno=8),
        divergences, 3,
    )
    assert len(divergences) == 1
    assert divergences[0].stream == "potion"


def test_claws_transform_screen_is_optional():
    """Claws.cs:24 builds `CardSelectorPrefs(prompt, 0, CardsVar(6))` — MinSelect
    **0**, MaxSelect 6 — with `RequireManualConfirmation`, so the player may
    confirm with fewer than 6 cards chosen (933T39V18D picked 5). The sim must
    surface that screen as skippable; a forced 6-of-6 transform puts an extra
    Maul in the deck and desyncs every later hand."""
    import random

    from sts2_rl.driver import SKIPPABLE_PURPOSES
    from sts2_rl.run import RunState

    seen: list[tuple[str, int]] = []

    def selector(purpose, candidates, count):
        seen.append((purpose, count))
        return candidates[:2]

    run = RunState(rng=random.Random(0), card_selector=selector)
    run.add_relic("claws")
    assert len(seen) == 1
    purpose, count = seen[0]
    assert count == 6
    assert purpose in SKIPPABLE_PURPOSES, purpose
    # Only the two cards the selector confirmed became Mauls.
    assert len([c for c in run.deck if c.id == "maul"]) == 2
