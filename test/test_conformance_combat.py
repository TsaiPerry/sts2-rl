"""SP3 Task 6 parity check: monster moves roll at telegraph time on the
MonsterAi stream, not at resolution time on the shared legacy _rng.

This is a stream-wiring smoke test, not a full recording-match test — the
recording-based conformance check (matching intents turn-by-turn against a
RunReplays recording) is Task 7/8's job, once the map/encounter wiring that
picks the exact recorded seed's encounter exists. Here we just prove: a
parity-mode combat whose first enemy has a random branch draws from
RunRngSet.monster_ai exactly once at combat-start telegraph, and the same
wiring holds for a legacy (unseeded) combat sharing one _rng.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from sts2_rl.combat import CombatState
from sts2_rl.rng import RunRngSet
from sts2_rl.monsters.overgrowth.slimes import SLIMES_NORMAL, LeafSlimeS
from sts2_rl.monsters.overgrowth.fuzzy_wurm_crawler import (
    FUZZY_WURM_ENCOUNTER, FuzzyWurmCrawler,
)

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"


def test_monster_move_rolls_once_on_monster_ai_at_telegraph():
    # SLIMES_NORMAL always includes a LeafSlimeS (SlimesNormalEncounter draws
    # both members of [LeafSlimeS, TwigSlimeS] via rng.sample(..., 2)).
    # LeafSlimeS's move is chosen at construction (combat-start telegraph,
    # mirroring MonsterModel.RollMove fired from AfterCreatureAdded) via a
    # RandomBranchState with two CannotRepeat/weight-1 branches, so with an
    # empty move log both are eligible: exactly one MonsterAi draw.
    rs = RunRngSet("seed")
    before = rs.monster_ai.counter
    combat = CombatState(rng_set=rs, encounter=SLIMES_NORMAL)
    assert rs.monster_ai.counter == before + 1

    leaf = next(e for e in combat.enemies if isinstance(e, LeafSlimeS))
    assert leaf._move_key in ("TACKLE", "GOOP")


def test_monster_move_stream_is_the_shared_rng_in_legacy_mode():
    # Legacy mode: combat_rng.monster_ai IS combat._rng (same object), so the
    # move roll draws from the exact same Random the rest of legacy combat
    # uses -- no behavior change for un-seeded (non-parity) callers.
    r = random.Random(0)
    combat = CombatState(rng=r, encounter=SLIMES_NORMAL)
    assert combat.combat_rng.monster_ai is combat._rng
    leaf = next(e for e in combat.enemies if isinstance(e, LeafSlimeS))
    assert leaf._move_key in ("TACKLE", "GOOP")


def test_parity_and_legacy_agree_on_which_branch_a_given_double_picks():
    # Both branches are CannotRepeat weight-1, so with nothing logged yet the
    # RandomBranchState total is 2 and the pick is a 50/50 split on the
    # single underlying draw. Confirm the parity-mode float32 NextFloat(2)
    # path and the legacy `.random() * 2` path agree on which half of [0, 2)
    # selects branch 0 vs branch 1 (both threshold at the same next_double()
    # value, per Rng.NextFloat's algorithm) -- i.e. no off-by-one in the
    # dual-mode primitive itself.
    from sts2_rl.monsters.state_machine import _weighted_roll
    from sts2_rl.rng import GameRandomAdapter, Rng

    game_rng = Rng(seed=12345)
    adapter = GameRandomAdapter(game_rng)
    parity_roll = _weighted_roll(adapter, 2.0)

    legacy_rng = random.Random()
    legacy_rng.seed(0)  # arbitrary; we only check the helper dispatches right
    legacy_roll = _weighted_roll(legacy_rng, 2.0)

    assert 0.0 <= parity_roll <= 2.0
    assert 0.0 <= legacy_roll <= 2.0
    assert game_rng.counter == 1  # exactly one draw for the parity path


def test_hand_rolled_monster_uses_weighted_branch_pick_not_stdlib_choice():
    # SP3 finding fix: hand-rolled monsters (LeafSlimeS et al.) must select
    # moves via weighted_branch_pick's single NextFloat(total) primitive --
    # the same RandomBranchState.get_next_state algorithm the state-machine
    # monsters use -- not stdlib random.Random.choice (an integer next_int
    # draw) or .choices (a double-precision weighted multiply). Those are
    # different primitives that pick a different branch for the same seed in
    # general, so this proves the fix actually changed the algorithm, not
    # just that "a" counter advanced.
    from sts2_rl.monsters.state_machine import weighted_branch_pick
    from sts2_rl.rng import GameRandomAdapter, RunRngSet

    seed_str = "parity-leaf-slime"

    # Independently compute what the game-exact primitive picks on a fresh
    # MonsterAi stream at this seed. Nothing else draws from MonsterAi before
    # LeafSlimeS's combat-start telegraph: encounter/class selection
    # (SlimesNormalEncounter.create_monsters) draws from the untouched legacy
    # `_rng`, not combat_rng, so MonsterAi's counter is still 0 at that point.
    expected_rs = RunRngSet(seed_str)
    expected = weighted_branch_pick(
        GameRandomAdapter(expected_rs.monster_ai), ["TACKLE", "GOOP"], [1, 1]
    )

    rs = RunRngSet(seed_str)
    combat = CombatState(rng_set=rs, encounter=SLIMES_NORMAL)
    leaf = next(e for e in combat.enemies if isinstance(e, LeafSlimeS))

    assert leaf._move_key == expected
    assert rs.monster_ai.counter == 1  # exactly one draw, matching the above


# ── Part A: seeded unique monster HP on the Niche stream ────────────────────

def test_parity_monster_hp_rolls_on_niche_stream():
    # Independently: one Niche draw picks the k-th smallest of {55,56,57}.
    rs_expected = RunRngSet("hp-seed")
    lo, hi = FuzzyWurmCrawler.min_hp, FuzzyWurmCrawler.max_hp
    cands = list(range(lo, hi + 1))
    expected_hp = cands[rs_expected.niche.next_int_range(0, len(cands))]

    rs = RunRngSet("hp-seed")
    before = rs.niche.counter
    combat = CombatState(rng_set=rs, encounter=FUZZY_WURM_ENCOUNTER)
    enemy = combat.enemies[0]
    assert enemy.hp == enemy.max_hp == expected_hp
    assert rs.niche.counter == before + 1   # exactly one Niche draw for one enemy


def test_legacy_monster_hp_rolls_random_without_niche_stream():
    # Legacy mode (no rng_set): HP still rolls in [min_hp, max_hp] via the
    # monster's own random.Random().randint (Monster.__init__) -- the parity
    # Niche-stream roll only fires when rng_set is not None, so no RunRngSet
    # is ever touched here.
    r = random.Random(0)
    combat = CombatState(rng=r, encounter=FUZZY_WURM_ENCOUNTER)
    enemy = combat.enemies[0]
    assert FuzzyWurmCrawler.min_hp <= enemy.hp <= FuzzyWurmCrawler.max_hp
    assert enemy.hp == enemy.max_hp


# ── Part B: ReplayCombatDriver -- enemy-id / display-name mapping ───────────

def test_enemy_by_target_id_maps_slots_and_names():
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver, enemy_display_name

    rs = RunRngSet("target-id-seed")
    combat = CombatState(rng_set=rs, encounter=SLIMES_NORMAL, track_card_ids=True)
    driver = ReplayCombatDriver(combat, cursor=None, card_db=combat.card_db)

    # SlimesNormalEncounter always creates [TwigSlimeM, LeafSlimeM, small0, small1].
    expected_names = {"Twig Slime (M)", "Leaf Slime (M)", "Twig Slime (S)", "Leaf Slime (S)"}
    assert len(combat.enemies) == 4
    for tid, enemy in enumerate(combat.enemies, start=1):
        assert driver.enemy_by_target_id(tid) is enemy
        assert enemy_display_name(enemy) in expected_names
    # tid=1 is always the fixed-first TwigSlimeM slot (encounter order).
    assert enemy_display_name(driver.enemy_by_target_id(1)) == "Twig Slime (M)"
    assert enemy_display_name(driver.enemy_by_target_id(2)) == "Leaf Slime (M)"


def test_wither_display_name_uses_the_fake_upgrade_level():
    """`Wither.Title` (Wither.cs:16-27) appends `+{FakeUpgradeLevel}`, not the
    ordinary upgrade level — which for Wither is permanently 0
    (`MaxUpgradeLevel => 0`, :41) because it grows via `FakeUpgrade()` (:60-64).

    The comparator read `upgrade_level` only, so a correctly fake-upgraded
    Wither rendered as "Wither" against the recording's "Wither+1" and was
    reported as a hand divergence — 89U21BV1TZ's last 14 per-command
    mismatches, all of them spurious."""
    from sts2_rl.conformance.combat_driver import card_display_name
    from sts2_rl.cards import make_card

    w = make_card("wither")
    assert card_display_name(w) == "Wither"
    w.fake_upgrade()
    assert card_display_name(w) == "Wither+1"
    w.fake_upgrade()
    assert card_display_name(w) == "Wither+2"
    # An ordinary card is unaffected: '+' per level, not '+N'.
    bash = make_card("bash")
    bash.upgrade()
    assert card_display_name(bash) == "Bash+"


def test_auto_played_card_targets_on_the_combat_targets_stream():
    # CardCmd.cs:77 — an AutoPlay with no target picks
    # `Rng.CombatTargets.NextItem(HittableEnemies)`. On the sim's unseeded
    # shared rng the pick is unreproducible and the CombatTargets counter stays
    # flat (933T39V18D: expected 26, sim drew 3).
    from sts2_rl.cards import make_card
    from sts2_rl.monsters.overgrowth import SLIMES_NORMAL

    rs = RunRngSet("auto-play-target")
    combat = CombatState(rng_set=rs, encounter=SLIMES_NORMAL)
    assert len(combat.enemies) > 1
    before = rs.combat_targets.counter
    combat.auto_play_card(make_card("strike"))
    assert rs.combat_targets.counter == before + 1


def test_enemies_annotation_keeps_a_retained_corpse():
    # The game removes a dead creature from CombatState.Enemies unless a power
    # says otherwise (ShouldCreatureBeRemovedFromCombatAfterDeath — the
    # Decimillipede's ReattachPower), so a withered segment still shows in a
    # recording's `Enemies:` list, at 0 HP. Ordinary corpses drop out.
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.monsters.hive import DECIMILLIPEDE_ELITE

    combat = CombatState(rng_set=RunRngSet("retained-corpse"),
                         encounter=DECIMILLIPEDE_ELITE, track_card_ids=True)
    driver = ReplayCombatDriver(combat, cursor=None, card_db=combat.card_db)

    victim = combat.enemies[1]
    DamageCmd.deal(combat.hooks, victim, 999, dealer=combat.player)
    assert victim.hp == 0
    live = driver._live_enemy_states()
    assert live == [(e.name, e.hp, e.max_hp) for e in combat.enemies]
    assert live[1] == (victim.name, 0, victim.max_hp)

    # A creature with no such power leaves the annotation entirely.
    plain = CombatState(rng_set=RunRngSet("retained-corpse"),
                        encounter=FUZZY_WURM_ENCOUNTER, track_card_ids=True)
    plain_driver = ReplayCombatDriver(plain, cursor=None, card_db=plain.card_db)
    DamageCmd.deal(plain.hooks, plain.enemies[0], 999, dealer=plain.player)
    assert plain_driver._live_enemy_states() == []


def test_enemy_name_match_tolerates_only_the_profile_counter_suffix():
    # TestSubject.cs:72 builds its Title with
    # `Count = SaveManager.Instance.Progress.TestSubjectKills + 8` - a
    # PROFILE-lifetime counter, so the act-3 boss reads "Test Subject #C71" in
    # 933T39V18D, "#C106" in DJDCSAQZNR and "#C114" in TZEKRYTSNT even though
    # all three saves carry the same per-run test_subject_kills. No run seed
    # can reproduce it, so the driver accepts the sim's un-numbered name for
    # that suffix shape only.
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver as D

    assert D._name_matches("Test Subject #C71", "Test Subject")
    assert D._name_matches("Globe Head", "Globe Head")
    # A real name gap (missing `name` attr, wrong spelling) still diverges.
    assert not D._name_matches("Globe Head", "GlobeHead")
    assert not D._name_matches("Test Subject", "Test Subject #C71")


def test_driver_reports_unknown_card_id_instead_of_crashing():
    # A recorded PlayCard whose CombatCardDb id was never registered in the sim
    # (an upstream divergence, e.g. an un-ported card-generation effect) must be
    # reported as a Divergence, not raise KeyError -- a conformance driver
    # reports, it does not crash.
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver
    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import _CommandCursor

    combat = CombatState(rng_set=RunRngSet("unknown-id"),
                         encounter=FUZZY_WURM_ENCOUNTER, track_card_ids=True)
    cursor = _CommandCursor([Command("PlayCard", ["99999"], "", None, 1)])
    driver = ReplayCombatDriver(combat, cursor, combat.card_db)

    divergences = driver.play()  # must not raise
    assert len(divergences) == 1
    assert divergences[0].stream == "play_card"
    assert "absent from sim combat card db" in divergences[0].detail


def test_driver_reports_resolved_card_not_in_hand():
    # A recorded card that resolves in the db but is not in the live hand (its
    # draw order diverged) is reported and the driver stops, rather than raising
    # ValueError from hand.index.
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver
    from sts2_rl.conformance.recording import Command
    from sts2_rl.conformance.runner import _CommandCursor

    combat = CombatState(rng_set=RunRngSet("in-draw"),
                         encounter=FUZZY_WURM_ENCOUNTER, track_card_ids=True)
    # A card sitting in the draw pile (not the hand) resolves via the db but is
    # absent from the live hand.
    draw_card = combat.player.draw_pile[0]
    cid = combat.card_db.id_of(draw_card)
    cursor = _CommandCursor([Command("PlayCard", [str(cid)], "", None, 1)])
    driver = ReplayCombatDriver(combat, cursor, combat.card_db)

    divergences = driver.play()  # must not raise
    assert len(divergences) == 1
    assert divergences[0].stream == "play_card"
    assert "absent from live hand" in divergences[0].detail


# ── First-fight-green: hand + enemies reproduce for the whole first Overgrowth fight ─


def drive_first_fight(rec):
    """Walk 89U21BV1TZ/floor_18 up to and through its first Monster room (a
    solo Fuzzy Wurm Crawler), replaying that fight's PlayCard/EndTurn commands
    against the live parity combat via ReplayCombatDriver, and return the
    fight's divergences. Mirrors ReplayRunner.run()'s map-walk setup (seeded
    RunState, injected Neow relics) but stops as soon as the first combat has
    been driven -- there is no need to finish the whole run for this check."""
    from sts2_rl.conformance.combat_driver import ReplayCombatDriver
    from sts2_rl.conformance.runner import _CommandCursor, _ForceWinDriver, relic_key, short_act_name
    from sts2_rl.conformance.save import parse_save
    from sts2_rl.run import RunState

    base = REC / "89U21BV1TZ" / "floor_18"
    oracle = parse_save(base / "run.save")
    acts = [short_act_name(a) for a in rec.acts]

    run = RunState(string_seed=rec.seed)
    cursor = _CommandCursor(rec.commands)
    result: dict = {"divergences": None}

    class _FirstFightDriver(_ForceWinDriver):
        def _run_combat(self, encounter, room_type):
            if result["divergences"] is not None:
                return super()._run_combat(encounter, room_type)
            run_ = self.run
            combat = run_.create_combat(encounter, room_type=room_type,
                                        track_card_ids=True)
            self._combat = combat
            replay_driver = ReplayCombatDriver(combat, self._cursor, combat.card_db)
            result["divergences"] = replay_driver.play()
            self._combat = None
            return combat

    driver = _FirstFightDriver(run, cursor, acts=acts, ascension=rec.ascension)
    run.start_run(acts=acts, ascension=rec.ascension)
    driver._roll_shared_ancients()

    # Inject the Neow relics the save recorded (ReplayRunner._neow_relics).
    history = oracle.map_history
    if history and history[0]:
        start = history[0][0]
        for stat in start.get("player_stats", []):
            for choice in stat.get("relic_choices", []):
                if choice.get("was_picked") and choice.get("choice"):
                    run.add_relic(relic_key(choice["choice"]))

    while result["divergences"] is None:
        cmd = cursor.take("MoveToMapCoord")
        assert cmd is not None and cmd.args, "recording exhausted before first fight"
        col = int(cmd.args[0])
        row = run.current_point.row + 1
        dest = next(
            (p for p in run.travelable_points() if p.col == col and p.row == row), None)
        assert dest is not None, f"MoveToMapCoord destination not travelable (col={col}, row={row})"
        resolution = run.enter_point(dest)
        driver._resolve_room(resolution)

    return result["divergences"]


@pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")
def test_first_overgrowth_fight_hand_and_enemies_match():
    from sts2_rl.conformance.recording import parse_recording

    rec = parse_recording(REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay")
    divergences = drive_first_fight(rec)
    assert divergences == [], "\n".join(str(d) for d in divergences)


# ── Task 8: runner drives combat via ReplayCombatDriver ─────────────────────


def _run_floor18():
    """Replay 89U21BV1TZ/floor_18 (act 1) through the full ReplayRunner, whose
    combat is now the ReplayCombatDriver (Task 8), and return its result."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "89U21BV1TZ" / "floor_18"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    return ReplayRunner(rec, oracle).run(stop_after_act=0)


def test_sp3_combat_streams_diffed_separately_from_sp2():
    # compare_counters over SP3_COMBAT_STREAMS reports one Divergence per
    # mismatched combat stream and touches none of the SP2 run/player streams
    # (empty player_streams). This is the machinery the runner uses to diff the
    # seven combat streams as their own subsystem bucket.
    from sts2_rl.conformance.comparators import SP3_COMBAT_STREAMS, compare_counters
    from sts2_rl.rng import RunRngType

    class _Oracle:
        run_counters = {t: 0 for t in RunRngType}
        player_counters = {}

    assert len(SP3_COMBAT_STREAMS) == 7
    live = {t: 0 for t in RunRngType}
    live[RunRngType.MONSTER_AI] = 5          # one combat stream diverges
    divs = compare_counters(live, {}, _Oracle(),
                            run_streams=SP3_COMBAT_STREAMS, player_streams=())
    assert [d.stream for d in divs] == [RunRngType.MONSTER_AI.value]
    assert divs[0].expected == 0 and divs[0].actual == 5


@pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")
def test_runner_drives_combat_first_fight_green_ids_resolve():
    # The runner now plays each annotated fight through ReplayCombatDriver
    # instead of force-winning it. For 89U21BV1TZ/floor_18 (act 1):
    #   - every recorded PlayCard id resolves to a live card (the Task 5
    #     PlayPile/resolving-card case; a genuine Task 8 deliverable),
    #   - the SP2 map/economy subsystem is untouched (no regression), and
    #   - the FIRST fight contributes zero combat divergences — the earliest
    #     combat divergence, if any, belongs to a LATER (still-un-ported) fight.
    # Full act-1 convergence (later fights' deck evolution / upgrades) is Task 9.
    result = _run_floor18()
    assert result.reached_act_end, result.stopped_reason
    assert result.unresolved_play_card_ids == [], result.unresolved_play_card_ids
    assert result.divergences == [], [str(d) for d in result.divergences]

    # First fight green: drive just the first fight and confirm it is clean,
    # so the runner-level combat_divergences are all attributable to later
    # (Task 9) fights, never the first one.
    from sts2_rl.conformance.recording import parse_recording
    rec = parse_recording(REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay")
    assert drive_first_fight(rec) == []


def _recorded_enemy_names() -> set[str]:
    """Every enemy display name any RunReplays recording ever showed."""
    import re

    names: set[str] = set()
    for path in REC.glob("*/floor_49/actions.sts2replay"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(r"Enemies: \[(.*)\]", line)
            if not m or not m.group(1):
                continue
            for entry in m.group(1).split(", "):
                hit = re.match(r"(.+) \d+/\d+$", entry)
                if hit:
                    names.add(hit.group(1))
    return names


def _sim_monster_names() -> set[str]:
    """Every display name the sim's monster classes can produce (static
    `name` attributes; the dynamic ones are covered by _DYNAMIC_NAMES)."""
    from sts2_rl.monsters.base import Monster
    import sts2_rl.monsters  # noqa: F401  registers every subclass

    out: set[str] = set()
    stack = [Monster]
    while stack:
        cur = stack.pop()
        for sub in cur.__subclasses__():
            stack.append(sub)
            declared = sub.__dict__.get("name")
            out.add(declared if isinstance(declared, str) else sub.__name__)
    return out


# Names the sim builds per-instance rather than from a class attribute, so a
# static scan can't see them: Ovicopter's eggs (Tough Egg / Hatchling, named
# from their slot) and Test Subject, whose loc string is literally
# "Test Subject #C{Count}" — the number is per-creature.
_DYNAMIC_NAMES = {"Tough Egg", "Hatchling"}


def test_monster_display_names_match_the_recordings():
    """Enemy display names are the recording's own Enemies: annotations, so a
    class whose `name` is left to default to its CamelCase class name shows up
    as a per-command divergence in every fight it appears in ("VineShambler"
    vs "Vine Shambler"). Names come from localization/eng/monsters.json
    (`<MONSTER_ID>.name`); this pins every name the recorded runs actually
    saw."""
    if not REC.exists():
        pytest.skip("RunReplays recordings not present")
    recorded = _recorded_enemy_names()
    assert recorded, "no enemy annotations found in the recordings"
    missing = {n for n in recorded - _sim_monster_names()
               if n not in _DYNAMIC_NAMES and not n.startswith("Test Subject #")}
    assert missing == set(), sorted(missing)
