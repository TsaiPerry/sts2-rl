"""harvest.py + RunDriver.on_combat_start (phase 3, Task 4).

Lane rules: every invariant test here must be shown to fail against a
mutated premise via a runtime monkeypatch in a SCRATCH script (never by
editing a tracked file) -- see the lane report for that evidence; this file
only contains the tests themselves.
"""
from __future__ import annotations

import json
import random

import faulthandler
import numpy as np
import pytest

import harvest
from sts2_rl.driver import DecisionKind, RunDriver, play_random_run, random_asker
from sts2_rl.monsters.overgrowth import ENCOUNTERS
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.snapshots import build_start_state, load_snapshots


# ═════════════════════════════════════════════════════════════════════════
# 1. Callback contract
# ═════════════════════════════════════════════════════════════════════════


def test_on_combat_start_fires_with_facts_matching_direct_reads():
    """`_run_combat` fires the callback once, right after `create_combat`
    (before the first combat decision is asked), with `(run, encounter)`
    such that reading deck/relics/hp/act/encounter straight off the two
    matches what `snapshot_from_run` (Task 2) would capture."""
    from sts2_rl.snapshots import snapshot_from_run

    rng = random.Random(3)
    run = RunState(rng=rng, max_hp=100000, hp=100000)
    fired: list[tuple] = []

    def on_combat_start(r, encounter, room_type):
        # Snapshot the facts a caller can read off `run`/`encounter` AT THIS
        # MOMENT -- this is the assertion under test: they must equal what a
        # direct read makes right after this call returns (nothing about
        # deck/relics/hp/act should have changed between "callback fires"
        # and "the caller reads run state").
        fired.append((
            r is run,
            [c.id for c in r.deck],
            [(rel.id) for rel in r.relics],
            r.hp,
            r.act_index,
            encounter.id,
            room_type,
        ))

    def scripted(request):
        return rng.choice(request.legal_actions())

    driver = RunDriver(run, scripted, on_combat_start=on_combat_start)
    deck_before = [c.id for c in run.deck]
    relics_before = [rel.id for rel in run.relics]
    hp_before = run.hp
    act_before = run.act_index
    encounter = ENCOUNTERS["fuzzy_wurm_weak"]

    driver._run_combat(encounter, RoomType.MONSTER)

    assert len(fired) == 1
    is_same_run, deck_ids, relic_ids, hp, act, enc_id, room_type = fired[0]
    assert is_same_run
    assert deck_ids == deck_before
    assert relic_ids == relics_before
    assert hp == hp_before
    assert act == act_before
    assert enc_id == encounter.id
    # Schema-2: the hook carries the driver's own room type.
    assert room_type == RoomType.MONSTER

    # And it agrees with the actual Task-2 builder the harvester calls.
    run2 = RunState(rng=random.Random(3), max_hp=100000, hp=100000)
    snap = snapshot_from_run(run2, encounter, room_type.name)
    assert [c.id for c in run2.deck] == deck_ids
    assert snap.encounter_id == enc_id
    assert snap.room_type == "MONSTER"


def test_on_combat_start_fires_once_per_combat_entered():
    rng = random.Random(11)
    run = RunState(rng=rng, max_hp=100000, hp=100000)
    calls = []

    def on_combat_start(r, encounter, room_type):
        calls.append(encounter.id)

    def scripted(request):
        return rng.choice(request.legal_actions())

    encounter = ENCOUNTERS["fuzzy_wurm_weak"]
    driver = RunDriver(run, scripted, on_combat_start=on_combat_start)
    driver._run_combat(encounter, RoomType.MONSTER)
    driver._run_combat(encounter, RoomType.MONSTER)
    assert calls == [encounter.id, encounter.id]


# ═════════════════════════════════════════════════════════════════════════
# 2. None default -- zero behavior change
# ═════════════════════════════════════════════════════════════════════════


def test_on_combat_start_none_is_zero_behavior_change():
    """Absent kwarg, explicit `on_combat_start=None`, and a genuine no-op
    callback must all produce byte-identical `RunResult`s for the same
    seed -- the hook must not perturb the RNG timeline or any decision."""
    absent = play_random_run(5)
    explicit_none = play_random_run(5, on_combat_start=None)
    noop = play_random_run(5, on_combat_start=lambda run, encounter, room_type: None)
    assert absent == explicit_none == noop


def test_on_combat_start_none_matches_pre_hook_driver_tests():
    """Cross-check against test_driver.py's own existing invariant
    (test_random_run_deterministic_under_seed): the hook's mere presence in
    the constructor signature must not change `play_random_run`'s output for
    ANY caller that doesn't pass it -- i.e. every driver test that predates
    this task stays green unmodified (verified by running test_driver.py
    alongside this file, see the lane report)."""
    a = play_random_run(42)
    b = play_random_run(42)
    assert a == b


# ═════════════════════════════════════════════════════════════════════════
# 3. End-to-end harvest
# ═════════════════════════════════════════════════════════════════════════


def test_harvest_end_to_end(tmp_path):
    out = tmp_path / "snaps.jsonl"
    log = tmp_path / "harvest.log"
    summary = harvest.harvest(
        episodes=2, seed=0, out=out, log=log, watchdog_secs=60,
    )

    assert summary["episodes"] == 2
    assert summary["snapshots_written"] > 0
    assert summary["snapshots_written"] == summary["combats_entered"]

    dataset = load_snapshots(out)
    assert len(dataset) == summary["snapshots_written"]

    seen_nonzero_decisions = False
    for i in range(len(dataset)):
        snap = dataset[i]
        # every snapshot round-trips through build_start_state without error
        kwargs = build_start_state(snap)
        assert kwargs["encounter"] is not None
        assert kwargs["max_hp"] == snap.max_hp

        prov = snap.provenance
        assert prov["seed"] in (0, 1)          # seed .. seed+episodes-1
        assert isinstance(prov["episode_decisions"], int)
        # Schema-2: floor/gold/room_type are first-class fields now.
        assert isinstance(snap.floor, int) and snap.floor >= 1
        assert isinstance(snap.gold, int)
        assert snap.room_type in ("MONSTER", "ELITE", "BOSS")
        if prov["episode_decisions"] > 0:
            seen_nonzero_decisions = True
    # Refutes the Task-2 placeholder (snapshot_from_run's own
    # provenance["episode_decisions"] = 0 default): at least one combat in a
    # 2-episode run is entered after some prior decision (Neow/map travel),
    # so a harvester that failed to overwrite the placeholder would read
    # all-zero here.
    assert seen_nonzero_decisions

    assert log.exists()
    log_lines = log.read_text().splitlines()
    assert len(log_lines) > 0
    seed_col, ep_col, dec_col = log_lines[0].split("\t")
    assert int(seed_col) == 0
    assert int(ep_col) == 0
    assert int(dec_col) >= 1


def test_harvest_cli_main_smoke(tmp_path):
    out = tmp_path / "cli_snaps.jsonl"
    log = tmp_path / "cli.log"
    summary = harvest.main([
        "--episodes", "1", "--seed", "7", "--out", str(out),
        "--log", str(log), "--watchdog-secs", "60",
    ])
    assert summary["snapshots_written"] >= 0
    dataset = load_snapshots(out)
    assert len(dataset) == summary["snapshots_written"]


# ═════════════════════════════════════════════════════════════════════════
# 4. Watchdog arming (never induce a real hang -- count the arm/cancel calls)
# ═════════════════════════════════════════════════════════════════════════


def test_watchdog_armed_and_cancelled_every_step(tmp_path, monkeypatch):
    dumps: list[float] = []
    cancels: list[int] = []

    def fake_dump_later(timeout, *, file=None, exit=False, repeat=False):
        dumps.append(timeout)

    def fake_cancel():
        cancels.append(1)

    monkeypatch.setattr(faulthandler, "dump_traceback_later", fake_dump_later)
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", fake_cancel)

    out = tmp_path / "snaps.jsonl"
    log = tmp_path / "watchdog.log"
    summary = harvest.harvest(
        episodes=1, seed=0, out=out, log=log, watchdog_secs=42,
    )

    assert len(dumps) > 0
    assert all(t == 42 for t in dumps)
    # one arm, one cancel per env.step() -- never left armed after a step.
    assert len(dumps) == len(cancels)
