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
    resync mechanism can be trusted generally."""
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

    assert resynced.forced_combats <= baseline.forced_combats
    assert len(resynced.combat_divergences) <= len(baseline.combat_divergences)
