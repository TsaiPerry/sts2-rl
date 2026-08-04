from __future__ import annotations

from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
BK = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")

# Per-seed floor-save roots. 933T has all 49 floors in the capture backup;
# 89U only has its 3 act-boundary saves (under Resources, same as the
# recordings) — enough to exercise the resync invariant on a second seed.
_FLOOR_ROOTS = {
    "933T39V18D": BK,
    "89U21BV1TZ": REC / "89U21BV1TZ",
}


def _floor_saves_for(seed: str) -> dict:
    from sts2_rl.conformance.save import parse_save
    root = _FLOOR_ROOTS[seed]
    return {int(p.name.split("_")[1]): parse_save(p / "run.save")
            for p in root.glob("floor_*") if (p / "run.save").exists()}


def _floor_saves():
    return _floor_saves_for("933T39V18D")


def test_sim_potion_id_maps_parity_pool_placeholders():
    """A potion the sim carries only as a pool-membership placeholder
    (potion_pools._ParityPotion — e.g. MazalethsGift / PowerPotion, which are
    in Character.PotionPool ∪ SharedPotionPool but the sim doesn't implement)
    must map to its snake_case id, NOT None.

    Root cause of the 933T act-2 potion cascade: the sim correctly generates
    the placeholder into a belt slot (e.g. MazalethsGift in slot 2 for all of
    act 2), but sim_potion_id only knew ALL_POTIONS (implemented potions), so
    the floor-potion diff read a correctly-held placeholder as a divergence and
    the resync then DROPPED it — un-filling a slot the game had full, so the
    sim went on to grab reward potions the full-belt game skipped
    (blessing_of_the_forge@39, power_potion@40, ...)."""
    from sts2_rl.conformance import idmap

    assert idmap.sim_potion_id("POTION.MAZALETHS_GIFT") == "mazaleths_gift"
    assert idmap.sim_potion_id("POTION.POWER_POTION") == "power_potion"
    assert idmap.sim_potion_id("POTION.BLESSING_OF_THE_FORGE") == \
        "blessing_of_the_forge"
    # An implemented potion still maps (unchanged behaviour).
    assert idmap.sim_potion_id("POTION.SPEED_POTION") == "speed_potion"
    # A genuinely unknown id is still None (reported, never crashes).
    assert idmap.sim_potion_id("POTION.NOT_A_REAL_POTION") is None


def test_make_pool_potion_builds_placeholder_for_unimplemented():
    """The resync rebuilds a belt from the save's slot ids; an id the sim does
    not implement must yield a _ParityPotion placeholder (carrying its id and a
    rarity) rather than KeyError-ing out of potions.make_potion. Implemented
    potions still build their real class.

    Every potion of the *Ironclad-reachable* pool (POTION_POOL) is implemented
    now — see test_potions.TestPoolCoverage — so the placeholder path is
    exercised by a cross-character potion id, which a save can still carry
    (Silent's Poison Potion here) and the pool never offers."""
    from sts2_rl.potion_pools import make_pool_potion
    from sts2_rl.potions import _POTION_CLASSES

    placeholder = make_pool_potion("poison_potion")
    assert placeholder.id == "poison_potion"
    assert placeholder.rarity == "common"     # default for a non-pool id
    assert "poison_potion" not in _POTION_CLASSES   # genuinely a placeholder

    real = make_pool_potion("mazaleths_gift")
    assert type(real).__name__ == "MazalethsGift"
    assert real.rarity == "rare"              # matches POTION_POOL


@pytest.mark.skipif(not (REC.exists() and BK.exists()), reason="fixtures absent")
def test_floor_checkpoints_and_resync_run_to_completion():
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    saves = _floor_saves()
    assert len(saves) == 49
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)
    floor_divs = [d for d in result.divergences if d.stream.startswith("floor_")]
    # Not asserting zero (the seed hasn't converged); asserting the MECHANISM:
    # checkpoints fired across the whole run and resync kept the replay alive
    # to the recorded end instead of dying to cascade damage.
    assert result.stopped_reason.startswith("reached act 2")
    checked_floors = {d.command_index for d in floor_divs}
    assert all(1 <= f <= 49 for f in checked_floors)


@pytest.mark.skipif(not (REC.exists() and BK.exists()), reason="fixtures absent")
def test_resync_skips_the_final_checkpointed_floor():
    """The final floor's backup save is an entry-style capture, structurally
    different from the whole-run END oracle DETECTORS 2/3 already check the
    post-room state against — comparing them can never converge (code
    review, 2026-08-04: recording a permanently-unwinnable diff there made a
    fully-converged replay print DIVERGENCES REMAIN forever). Both the diff
    AND the resync are skipped for this one floor; its post-state is already
    covered elsewhere (DETECTORS 2/3 against the true run-END oracle)."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    b = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    saves = _floor_saves()
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)
    # The run-end stream counters must now match exactly as they do in the
    # unresynced gate — the final-floor pin was the sole source of the
    # Shuffle 892-vs-909 phantom.
    assert [d for d in result.combat_divergences if d.command_index == -1] == []
    # No floor_* divergence may carry the final floor's own number — the
    # diff there is unwinnable by construction (two legitimately different
    # oracles for that floor), so it must not be recorded at all.
    final_floor = max(saves)
    assert [d for d in result.divergences
            if d.stream.startswith("floor_") and d.command_index == final_floor] == []


@pytest.mark.skipif(not (REC.exists() and BK.exists()), reason="fixtures absent")
def test_floor_47_backup_save_is_excluded_as_an_inconsistent_capture():
    """933T floor_47's backup save (`_FLOOR_ROOTS`) records hp=74 — a value
    that matches NEITHER the run-end save's room_stats_by_act entry for that
    room (post-room hp 80, act 2 room 12 exit) NOR its entry hp (66, the
    value tools/oracle_semantics_probe.py's `hist[F-1]`/`entry-arith` columns
    both independently derive) NOR any other reachable number. Every other
    one of the 49 backup floors in that probe table lines up with one of
    those two references (dominantly ENTRY); 47 (and its stale duplicate 48)
    are the sole exceptions. Since the sim's own room-12 HP (66) agrees with
    the history-derived value, the 74 in the floor_47 backup is a mid-room /
    wrong-moment capture artifact, not ground truth — `_check_floor_state`
    must skip it exactly like a stale save, leaving the floor unchecked
    (still safe: the next non-excluded checkpoint compares full state again)."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / "933T39V18D" / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=_floor_saves(), resync_floors=True)
    floor_47_hp_divs = [
        d for d in result.divergences
        if d.stream == "floor_hp" and d.command_index == 47
    ]
    assert floor_47_hp_divs == []


def test_is_inconsistent_floor_save_requires_sim_agreement_with_history():
    """Code review Critical fix (2026-08-04): excluding a floor must not rely
    on oracle-internal evidence alone (backup vs history/arithmetic) — that
    could silently swallow a REAL divergence on some future floor whose
    backup happens to be self-inconsistent for an unrelated reason. The
    floor is excluded ONLY when the backup is unreachable from the history
    references AND the live sim (`run.hp`) agrees with the one reachable
    reference. If the sim ALSO disagrees, the floor is NOT excluded — the
    diff must be recorded so it can be investigated, not silently dropped.

    Unit-level, no fixtures required: constructs a minimal two-point
    `room_stats_by_act` directly (`ReplayRunner.__new__` + a bare `oracle`)
    so both branches are exercised deterministically without depending on
    which real recording floor happens to be inconsistent."""
    from types import SimpleNamespace

    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import RoomStats, SaveOracle

    def room(hp, damage_taken=0, hp_healed=0):
        return RoomStats(map_point_type="combat", current_hp=hp, max_hp=80,
                          damage_taken=damage_taken, hp_healed=hp_healed,
                          current_gold=0, gold_gained=0, gold_spent=0,
                          gold_lost=0, gold_stolen=0, max_hp_gained=0,
                          max_hp_lost=0)

    # floor 1 (prev): hp 70. floor 2 (cur): hp 50, damage_taken 20, hp_healed
    # 0 -> arith = 50 + 20 - 0 = 70, matching prev — history is internally
    # consistent here; the only reachable reference for a floor-2 backup is
    # 70 (== prev.current_hp == arith; cur.current_hp itself is 50).
    prev, cur = room(70), room(50, damage_taken=20)
    runner = ReplayRunner.__new__(ReplayRunner)
    runner.oracle = SaveOracle(
        run_seed="x", player_seed=0, ascension=0, acts=[],
        current_act_index=0, run_counters={}, player_counters={},
        room_stats_by_act=[[prev, cur]])

    inconsistent_backup = SimpleNamespace(player_current_hp=999)

    # Sim agrees with the one reachable reference (70) -> exclude.
    sim_agrees = SimpleNamespace(hp=70)
    assert runner._is_inconsistent_floor_save(2, inconsistent_backup, sim_agrees)

    # Sim ALSO disagrees (neither 50, 70, nor 999) -> do NOT exclude; the
    # divergence must surface, not be silently swallowed.
    sim_disagrees = SimpleNamespace(hp=12345)
    assert not runner._is_inconsistent_floor_save(
        2, inconsistent_backup, sim_disagrees)

    # A backup that DOES match a reachable reference is never excluded,
    # regardless of what the sim did (nothing to exclude — it's consistent).
    consistent_backup = SimpleNamespace(player_current_hp=70)
    assert not runner._is_inconsistent_floor_save(2, consistent_backup, sim_agrees)


@pytest.mark.parametrize("seed", [
    pytest.param("933T39V18D", marks=pytest.mark.skipif(
        not (REC.exists() and BK.exists()), reason="fixtures absent")),
    pytest.param("89U21BV1TZ", marks=pytest.mark.skipif(
        not (REC.exists() and (REC / "89U21BV1TZ").exists()),
        reason="fixtures absent")),
])
def test_resync_does_not_degrade_replay_vs_no_floor_saves_baseline(seed):
    """Critical-finding regression guard (post-review fix): `floor_saves` +
    `resync_floors=True` must never make the replay WORSE than the same
    replay with no `floor_saves` at all. Before the stale-save-detection fix,
    933T39V18D at stop_after_act=2 measured forced_combats 1->8 and
    combat_divergences 10->126 (a stale `run.save` — not re-exported after
    its room resolved, e.g. floor_5 duplicating floor_4's pre-purchase state
    — was treated as ground truth and resync rolled back correct live state).
    Runs both arms directly (~1.5s total per seed) rather than pinning
    absolute numbers, so this catches any future regression of the same
    shape, not just today's exact counts.

    Parametrized over both conformance seeds: 933T39V18D (49 per-floor
    saves, the case the stale-save fix was built against) and 89U21BV1TZ
    (only its 3 act-boundary saves) — the risk this guards against is
    per-seed, so the invariant must hold on more than one seed before the
    resync mechanism can be trusted generally.

    WHOLE-RUN STREAM COUNTERS ARE EXCLUDED, and not to make the test pass.
    The two arms are not comparable on them: `resync_floors` pins each stream
    to the FLOOR-ENTRY snapshot in `_FLOOR_ROOTS[seed]/floor_N/run.save`,
    while `combat_divergences`' counter leg compares the run's end state to
    `REC/<seed>/floor_49/run.save`, which is a DIFFERENT capture taken at run
    END — for 933T39V18D, Shuffle 892 at floor-49 entry vs 909 at the end. So
    once the unresynced arm is exact (as it became when the card-db and
    `List<T>.Sort()` fixes landed and 933T's baseline counters went to zero
    divergences), the resynced arm is pinned to the earlier snapshot on the
    last floor and can only lose. What the guard was built to catch — the
    stale-save cascade — showed up as forced_combats and as PER-COMMAND
    mismatches (10 -> 126), and both are still compared below."""
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.runner import ReplayRunner
    from sts2_rl.conformance.save import parse_save

    base = REC / seed / "floor_49"
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")
    saves = _floor_saves_for(seed)

    baseline = ReplayRunner(rec, oracle).run(stop_after_act=2)
    resynced = ReplayRunner(rec, oracle).run(
        stop_after_act=2, floor_saves=saves, resync_floors=True)

    def per_command(result):
        return [d for d in result.combat_divergences if d.command_index != -1]

    assert resynced.forced_combats <= baseline.forced_combats
    assert len(per_command(resynced)) <= len(per_command(baseline))
