"""Tests for sts2_rl/snapshots.py (phase-3 R11 Task 2 — snapshot module).

Written against the actual engine, not the plan's premises: every field the
brief assumed was checked against the code that reads it (`full_env.py`'s
card/relic/potion/hp obs builders), and the deviations that check turned up
are recorded in snapshots.py's module docstring, not silently absorbed.
"""
from __future__ import annotations

import json

import pytest

from sts2_rl.afflictions import make_affliction
from sts2_rl.cards import make_card
from sts2_rl.combat import CombatState
from sts2_rl.enchantments import make_enchantment
from sts2_rl.full_env import _clip01, _potions_rows, _relic_rows, card_instance_row
from sts2_rl.potions import make_potion
from sts2_rl.previews import preview_card_energy_cost
from sts2_rl.relic_obs import _BOTH, _COUNTER_ONLY, relic_row
from sts2_rl.relics import make_relic
from sts2_rl.run import RunState
from sts2_rl.snapshots import (
    _COUNTER_REBUILD,
    CardSnap,
    RelicSnap,
    Snapshot,
    build_start_state,
    encounter_registry,
    load_snapshots,
    save_snapshots,
    snapshot_from_run,
)


def _deck_rows_sorted(state: CombatState):
    rows = [
        card_instance_row(c, 0, preview_card_energy_cost(state, c))
        for c in state.player.all_cards
    ]
    return sorted(rows, key=lambda r: (tuple(r[0]), tuple(r[1])))


def _hp_ratio(state: CombatState) -> float:
    p = state.player
    return _clip01(p.hp / max(1, p.max_hp))


# ── JSON round trip ─────────────────────────────────────────────────────


def _sample_snapshot() -> Snapshot:
    return Snapshot(
        deck=(
            CardSnap("strike", True, None, "ringing", 2),
            CardSnap("defend", False, "glam", None, None),
        ),
        relics=(RelicSnap("girya", 2), RelicSnap("lizard_tail", 0)),
        hp=40,
        max_hp=70,
        potion_slots=(None, "fire_potion", None),
        act=1,
        encounter_id="flyconid_normal",
        gold=137,
        floor=12,
        room_type="MONSTER",
        provenance={"seed": "ABCD", "ascension": 10, "episode_decisions": 5},
    )


def test_round_trip_lossless(tmp_path):
    snap = _sample_snapshot()
    path = tmp_path / "snaps.jsonl"
    save_snapshots(path, [snap])
    loaded = load_snapshots(path)
    assert len(loaded) == 1
    assert loaded[0] == snap


def test_save_snapshots_writes_header_line_first(tmp_path):
    path = tmp_path / "snaps.jsonl"
    save_snapshots(path, [_sample_snapshot(), _sample_snapshot()])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"snapshot_schema": 2}
    assert len(lines) == 3   # header + 2 snapshots


def test_load_snapshots_rejects_schema_1(tmp_path):
    """v1 banks predate gold/floor/room_type — refused loudly, re-harvest."""
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps({"snapshot_schema": 1}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot_schema 1"):
        load_snapshots(path)


def test_load_snapshots_rejects_schema_mismatch(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"snapshot_schema": 999}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="999"):
        load_snapshots(path)


def test_load_snapshots_rejects_missing_header(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"deck": []}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_snapshots(path)


def test_dataset_sample_and_indexing(tmp_path):
    import random

    a, b = _sample_snapshot(), _sample_snapshot()
    b = Snapshot(**{**b.__dict__, "hp": 1})
    path = tmp_path / "snaps.jsonl"
    save_snapshots(path, [a, b])
    ds = load_snapshots(path)
    assert len(ds) == 2
    assert ds[0].hp == 40
    assert ds[1].hp == 1
    rng = random.Random(0)
    drawn = {ds.sample(rng).hp for _ in range(20)}
    assert drawn == {40, 1}


# ── encounter_registry ──────────────────────────────────────────────────


def test_encounter_registry_covers_all_acts_including_elites_bosses():
    reg = encounter_registry()
    # One boss per act package (overgrowth/underdocks/hive/glory).
    for boss_id in (
        "ceremonial_beast_boss", "waterfall_giant_boss",
        "kaiser_crab_boss", "queen_boss",
    ):
        assert boss_id in reg, boss_id
    # An elite from each act, spot-checked.
    for elite_id in ("bygone_effigy_elite", "terror_eel_elite",
                      "decimillipede_elite", "knights_elite"):
        assert elite_id in reg, elite_id
    # Every registry value's own id matches the key it's stored under.
    assert all(k == e.id for k, e in reg.items())
    assert len(reg) >= 70   # 80 measured 2026-08-02; a floor, not a pin


def test_encounter_registry_contains_dense_vegetation_event():
    """Fix report 2 regression pin: `runs/snapshots/random-v1.jsonl` (the
    harvested run-env dataset) contains snapshots with
    `encounter_id == "dense_vegetation_event"` — a combat the Dense
    Vegetation EVENT launches (`events/dense_vegetation.py`'s FIGHT option),
    not a map-room encounter. `encounter_registry()` originally only walked
    the four per-act monster packages, so this id raised `KeyError` out of
    `build_start_state` on a live, harvested snapshot."""
    reg = encounter_registry()
    assert "dense_vegetation_event" in reg
    assert reg["dense_vegetation_event"].id == "dense_vegetation_event"


def test_encounter_registry_covers_every_event_encounter():
    """Ties `encounter_registry()` to the actual source of truth for
    event-launched combats: every `Encounter` INSTANCE `sts2_rl.events`
    itself re-exports, discovered by WALKING `events.__all__` at test time
    (not a second hand-typed literal — see below for why that distinction
    matters) and filtering by `isinstance(..., Encounter)` (`events.__all__`
    also names every registered `Event` subclass, e.g. `DenseVegetation`,
    which this filters back out).

    Why a walk and not a literal: an earlier version of this test compared
    `snapshots._EVENT_ENCOUNTERS` against a SECOND hand-typed set of the same
    7 names — a tautology that could not fail no matter how far
    `_EVENT_ENCOUNTERS` drifted from the real export list, because both sides
    were maintained by the same hand. Proof (code review, R1): adding a
    fabricated new event-encounter constant to `events.__all__` still passed
    it. `discovered_ids` below is instead produced by inspecting the package
    namespace itself, so a new export that `snapshots._EVENT_ENCOUNTERS`
    hasn't picked up changes what this test computes, not just what it
    asserts against.

    This walk and `snapshots._EVENT_ENCOUNTERS` are still two INDEPENDENT
    processes, not one shared function reused on both sides (which would let
    a shared bug pass both): `_EVENT_ENCOUNTERS` was hand-built by reading
    every event module's source directly (`sts2_rl/events/*.py`,
    `sts2_rl/monsters/**/*.py`); this walk instead reads the already-built
    `sts2_rl.events` package namespace at runtime. A fixed floor
    (`dense_vegetation_event` present, count >= 7) is asserted first and
    independently of the walk, so an accidentally-empty or broken walk
    (e.g. `__all__` renamed) cannot pass this test by vacuously agreeing with
    an equally-empty `_EVENT_ENCOUNTERS`.

    Mirrors `test_counter_rebuild_covers_every_relic_obs_counter_table_entry`
    below in spirit: an exact set-equality check against a hand-maintained
    table, at test time rather than import time (same rationale — no
    per-import tax on production code paths that never touch this).
    """
    import sts2_rl.events as _events_pkg
    from sts2_rl.monsters import Encounter as _Encounter
    from sts2_rl.snapshots import _EVENT_ENCOUNTERS

    # Genuine discovery: every name events.__all__ actually exports whose
    # bound value IS an Encounter instance (not merely named like one).
    # `Encounter` is an unhashable dataclass, so collect ids directly rather
    # than a set of instances.
    discovered_ids = {
        getattr(_events_pkg, name).id
        for name in _events_pkg.__all__
        if isinstance(getattr(_events_pkg, name, None), _Encounter)
    }

    # Fixed floor, independent of the walk succeeding at all (guards against
    # a broken/vacuous walk trivially matching an equally-broken
    # _EVENT_ENCOUNTERS).
    assert "dense_vegetation_event" in discovered_ids
    assert len(discovered_ids) >= 7

    actual_ids = {e.id for e in _EVENT_ENCOUNTERS}
    assert discovered_ids == actual_ids, (
        "snapshots._EVENT_ENCOUNTERS has drifted from the Encounter "
        f"instances sts2_rl.events actually exports: discovered "
        f"{sorted(discovered_ids)}, snapshots._EVENT_ENCOUNTERS has "
        f"{sorted(actual_ids)}"
    )
    reg = encounter_registry()
    missing = discovered_ids - set(reg)
    assert not missing, (
        f"encounter_registry() is missing event encounter(s): {sorted(missing)}"
    )


def test_build_start_state_unknown_encounter_id_raises_keyerror():
    snap = Snapshot(
        deck=(), relics=(), hp=1, max_hp=1, potion_slots=(),
        act=0, encounter_id="does_not_exist", provenance={},
    )
    with pytest.raises(KeyError, match="does_not_exist"):
        build_start_state(snap)


# ── Obs-level fidelity ──────────────────────────────────────────────────


def test_obs_level_fidelity_round_trip():
    """Build a CombatState with a custom deck (one upgraded card, one
    afflicted card), a relic with a nonzero counter, custom hp/max_hp and a
    gapped potion belt; express the same facts as a Snapshot via a minimal
    RunState (test_driver.py's `fresh_run` pattern); build_start_state it;
    build a second CombatState from the result; assert the deck/relic/
    potion/hp obs rows agree."""
    def _build_deck() -> list:
        upgraded_strike = make_card("strike")
        upgraded_strike.upgrade()
        afflicted_defend = make_card("defend")
        afflicted_defend.affliction = make_affliction("ringing", 3)
        return [upgraded_strike, afflicted_defend, make_card("bash")]

    def _build_relic():
        relic = make_relic("girya")
        relic.times_lifted = 2
        return relic

    def _build_potions() -> list:
        return [None, None, make_potion("fire_potion")]   # gap at 0/1

    # Must be a REAL registered encounter (build_start_state resolves
    # snap.encounter_id through encounter_registry(), which a throwaway
    # dummy Encounter is never a member of).
    encounter = encounter_registry()["fuzzy_wurm_crawler"]
    # `source` and `run` deliberately use SEPARATE object graphs (not shared
    # instances) so an identity-only bug in CardSnap/RelicSnap can't be
    # masked by both sides pointing at the same live objects.
    source = CombatState(
        starting_deck=_build_deck(), encounter=encounter, relics=[_build_relic()],
        potions=_build_potions(), max_hp=88, current_hp=55,
    )
    run = RunState(
        deck=_build_deck(), relics=[_build_relic()],
        max_hp=88, hp=55, potions=_build_potions(),
    )

    snap = snapshot_from_run(run, encounter, "MONSTER")
    assert snap.encounter_id == "fuzzy_wurm_crawler"
    assert snap.hp == 55 and snap.max_hp == 88
    assert snap.potion_slots == (None, None, "fire_potion")
    assert any(r.id == "girya" and r.counter == 2 for r in snap.relics)
    # Schema-2 run-level facts.
    assert snap.room_type == "MONSTER"
    assert snap.gold == run.gold
    assert snap.floor == run.total_floor

    kwargs = build_start_state(snap)
    rebuilt = CombatState(
        starting_deck=kwargs["deck_cards"], encounter=kwargs["encounter"],
        relics=kwargs["relics"],
        potions=[
            make_potion(pid) if pid is not None else None
            for pid in kwargs["potion_slots"]
        ],
        max_hp=kwargs["max_hp"], current_hp=kwargs["current_hp"],
    )

    assert _deck_rows_sorted(source) == _deck_rows_sorted(rebuilt)
    assert _relic_rows(source) == _relic_rows(rebuilt)
    assert _potions_rows(source) == _potions_rows(rebuilt)
    assert _hp_ratio(source) == _hp_ratio(rebuilt)
    assert source.player.hp == rebuilt.player.hp
    assert source.player.max_hp == rebuilt.player.max_hp


def test_obs_level_fidelity_round_trip_pins_flag_relic_loss():
    """PINS the documented limitation from snapshots.py's module docstring
    (deviation #3): `RelicSnap` is locked to `{id, counter}` per phase-3
    Locked Decision 1, and `relic_obs.relic_row` actually returns
    `(counter, flag)` — so a flag-bearing relic's latched flag does not
    survive a `Snapshot`/`build_start_state` round trip. This is silent-
    WRONG, not silent-absent: `RelicSnap.rebuild()` produces a fresh, unused
    relic via `make_relic`, so a latched flag reads back as 0.

    `test_obs_level_fidelity_round_trip` (above) never demonstrates this
    because its only relic, `girya`, is counter-only (relic_obs._COUNTER_ONLY)
    and has no flag half at all. This test uses `lizard_tail`
    (relic_obs._FLAG_ONLY — `is_used_up`, counter always 0) specifically
    latched (`is_used_up = True`) and asserts the rebuilt obs relic row
    differs from the source's in EXACTLY the flag column: id and counter
    columns match, the flag column does not.

    This is a documented-loss test, not a bug report: if a future change
    makes `RelicSnap` carry the flag (closing the gap), the `r_aux[1] == 0.0`
    / `s_aux != r_aux` assertions below should start failing loudly, forcing
    whoever lands that fix to consciously flip this test rather than have it
    silently keep passing over changed behavior.
    """
    relic = make_relic("lizard_tail")
    relic._used = True   # `is_used_up` is a read-only property over `_used`
    assert relic.is_used_up is True   # sanity: the flag is actually latched

    encounter = encounter_registry()["fuzzy_wurm_crawler"]
    source = CombatState(
        starting_deck=[make_card("strike")], encounter=encounter,
        relics=[relic], potions=[], max_hp=50, current_hp=50,
    )
    run = RunState(
        deck=[make_card("strike")], relics=[make_relic("lizard_tail")],
        max_hp=50, hp=50, potions=[],
    )
    run.relics[0]._used = True

    snap = snapshot_from_run(run, encounter, "MONSTER")
    assert snap.relics == (RelicSnap("lizard_tail", 0),)   # counter half: 0, as expected

    kwargs = build_start_state(snap)
    rebuilt = CombatState(
        starting_deck=kwargs["deck_cards"], encounter=kwargs["encounter"],
        relics=kwargs["relics"], potions=[],
        max_hp=kwargs["max_hp"], current_hp=kwargs["current_hp"],
    )

    source_rows = _relic_rows(source)
    rebuilt_rows = _relic_rows(rebuilt)
    assert len(source_rows) == len(rebuilt_rows) == 1
    (s_id, s_aux), (r_id, r_aux) = source_rows[0], rebuilt_rows[0]

    assert s_id == r_id                 # relic identity: preserved
    assert s_aux[0] == r_aux[0] == 0.0  # counter column: lizard_tail is flag-only, always 0
    assert s_aux[1] == 1.0              # source: flag latched (is_used_up == True)
    assert r_aux[1] == 0.0              # rebuilt: flag SILENTLY REVERTED — the documented loss
    assert s_aux != r_aux               # the obs row differs, and only in the flag column


def test_card_snap_round_trips_upgrade_enchantment_affliction():
    card = make_card("strike")
    card.upgrade()
    card.enchantment = make_enchantment("glam")
    card.affliction = make_affliction("ringing", 4)

    snap = CardSnap.from_card(card)
    assert snap == CardSnap("strike", True, "glam", "ringing", 4)

    rebuilt = snap.rebuild()
    assert rebuilt.upgrade_level == 1
    assert rebuilt.enchantment is not None and rebuilt.enchantment.id == "glam"
    assert rebuilt.affliction is not None
    assert rebuilt.affliction.id == "ringing"
    assert rebuilt.affliction.amount == 4
    # v20 regression: BOTH riders must carry the back-reference the real
    # attach paths set (enchantments.attach_internal / CardCmd.afflict) —
    # a one-directional attach left enchantment.card None, which crashed
    # `card.downgrade()` (it calls enchantment.modify_card()) the first time
    # a Knights-elite Dampen hit an enchanted card in a drill episode, and
    # silently deadened afflicted-card hooks (hook_contains reads
    # affliction.card).
    assert rebuilt.enchantment.card is rebuilt
    assert rebuilt.affliction.card is rebuilt


def test_rebuilt_enchanted_card_survives_downgrade():
    """The v20 s23 crash, reproduced at the unit level: Dampen's
    `CardCmd.downgrade` walks `card.downgrade()` ->
    `enchantment.modify_card()`, which dies if the rebuild left the
    enchantment's card pointer unset."""
    from sts2_rl.cards import make_card as _mk

    live = _mk("strike")
    live.upgrade()
    live.enchantment = make_enchantment("glam")   # harvest-side attach shape
    rebuilt = CardSnap.from_card(live).rebuild()
    assert rebuilt.upgrade_level == 1
    rebuilt.downgrade()                            # must not raise
    assert rebuilt.upgrade_level == 0
    assert rebuilt.enchantment is not None and rebuilt.enchantment.id == "glam"


@pytest.mark.parametrize(
    "relic_id, attr, value",
    [
        ("girya", "times_lifted", 3),
        ("sword_of_stone", "elites_defeated", 5),
        ("toy_box", "combats_seen", 2),
    ],
)
def test_relic_snap_round_trips_persistent_counters(relic_id, attr, value):
    relic = make_relic(relic_id)
    setattr(relic, attr, value)
    counter_before, _ = relic_row(relic, in_combat=True)

    snap = RelicSnap.from_relic(relic)
    assert snap.counter == counter_before

    rebuilt = snap.rebuild()
    assert relic_row(rebuilt, in_combat=True) == (counter_before, 0)


def test_relic_snap_true_inversion_round_trips():
    """silver_crucible/winged_boots/wongos_mystery_ticket invert their raw
    counter (`max(0, N - x)`) — the reverse table must actually invert, not
    just copy, or this would silently under/over-count."""
    relic = make_relic("winged_boots")
    relic.times_used = 1   # displayed counter = max(0, 3-1) = 2
    snap = RelicSnap.from_relic(relic)
    assert snap.counter == 2
    rebuilt = snap.rebuild()
    assert rebuilt.times_used == 1
    assert relic_row(rebuilt, in_combat=True)[0] == 2


# ── _COUNTER_REBUILD completeness ───────────────────────────────────────


def test_counter_rebuild_covers_every_relic_obs_counter_table_entry():
    """`_COUNTER_REBUILD` (snapshots.py:200-235) is a hand-maintained table
    reverse-engineered from `relic_obs.py`'s own counter tables
    (`_COUNTER_ONLY`, 28 entries, and `_BOTH`, 4 entries) — nothing in the
    code ties the two together. If a future relic is added to either
    `relic_obs` table without a matching `_COUNTER_REBUILD` entry,
    `RelicSnap.rebuild`'s `spec = _COUNTER_REBUILD.get(self.id); if spec is
    not None: ...` silently no-ops: the relic's counter just stays 0 forever
    after any snapshot-started episode, with no error and no other test
    failure — discoverable only by noticing a specific relic behaves oddly
    in training. This test closes that gap with a loud, exact set-equality
    check.

    Mechanism choice: this is a TEST-time assertion (test/test_snapshots.py),
    not a module-import-time one (inside sts2_rl/snapshots.py itself).
    A module-level assertion would run on every import of `snapshots.py`,
    including in production training/eval code paths — paying a (small but
    nonzero, and non-obvious to a caller) cost on every process start, and
    turning a maintenance mismatch between two files into a hard crash for
    anyone merely importing the module, even code that never touches
    relic counters. A test-time assertion is the smallest mechanism that is
    still honest: it fails loudly in CI (this is exactly what CI is for),
    at development time, for the people actually able to fix the mismatch,
    without adding runtime risk to every import.

    Exact set equality (not just `expected <= actual`, i.e. not just "no
    missing entries") is deliberate: an `extra` entry (present in
    `_COUNTER_REBUILD` but no longer in either `relic_obs` table) is dead
    code that silently no-ops on the OTHER side (`RelicSnap.rebuild` would
    call a setter for a relic `relic_obs.relic_row` no longer reads a
    counter from at all) and is exactly the same class of "the two tables
    drifted apart" bug this test exists to catch — so both directions are
    checked and both are worth failing loudly on.
    """
    expected = set(_COUNTER_ONLY) | set(_BOTH)
    actual = set(_COUNTER_REBUILD)
    missing = expected - actual
    extra = actual - expected
    assert not missing, (
        "relic_obs.py has counter-bearing relic(s) with no snapshots.py "
        f"_COUNTER_REBUILD entry (silently no-ops on rebuild): {sorted(missing)}"
    )
    assert not extra, (
        "snapshots.py._COUNTER_REBUILD has entries for relic(s) relic_obs.py "
        f"no longer treats as counter-bearing (stale/dead code): {sorted(extra)}"
    )
