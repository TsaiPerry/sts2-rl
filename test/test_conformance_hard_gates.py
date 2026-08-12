"""The hard gates: triage's `converged` predicate, asserted by the suite for
both Ironclad seeds, both resync arms. `sts2_rl.conformance.triage.assess` is
the ONE definition of converged — `tools/converge_triage.py` prints it and
these tests assert it, so the tool and the suite cannot disagree.

The four other-character seeds are permanently out of scope here (Ironclad-only
sim; see test_conformance_player_state.py's xfail table)."""
from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.conformance.triage import assess

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
BK = Path(r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording")
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

IRONCLAD_SEEDS = ["89U21BV1TZ", "933T39V18D"]


def test_assess_flags_each_component():
    from sts2_rl.conformance.comparators import Divergence
    from sts2_rl.conformance.runner import ReplayResult

    r = ReplayResult(divergences=[], run_counters={}, player_counters={},
                     rooms_walked=0, reached_act_end=True,
                     stopped_reason="", forced_combats=0)
    assert assess(r).clean
    r.forced_combats = 2
    v = assess(r)
    assert not v.clean and any("forced_combats" in s for s in v.reasons)
    r.forced_combats = 0
    r.divergences.append(Divergence("room_hp", 12, 66, 74, ""))
    assert not assess(r).clean
    r.divergences.clear()
    assert not assess(r, tripwire_bug_sites={("run.py", 1, "f", ""): 3}).clean


def _floor_saves_for(seed):
    roots = {"933T39V18D": BK, "89U21BV1TZ": REC / "89U21BV1TZ"}
    return {int(p.name.split("_")[1]): parse_save(p / "run.save")
            for p in roots[seed].glob("floor_*") if (p / "run.save").exists()}


def _act_checkpoints(seed):
    ck = {}
    for act, fl in {0: "floor_18", 1: "floor_34", 2: "floor_49"}.items():
        f = REC / seed / fl / "run.save"
        if f.exists():
            o = parse_save(f)
            ck[act] = (o.player_current_hp, o.player_max_hp)
    return ck


def _replay(seed, resync):
    import sts2_rl.run as run_mod
    from sts2_rl.conformance.tripwire import Tripwire
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    tw = Tripwire()
    orig = run_mod.RunState.__init__

    def patched(self, *a, **kw):
        orig(self, *a, **kw)
        tw.install(self.rng)

    run_mod.RunState.__init__ = patched
    try:
        result = ReplayRunner(rec, oracle).run(
            stop_after_act=2,
            player_checkpoints=_act_checkpoints(seed),
            resync_player=resync,
            floor_saves=_floor_saves_for(seed) if resync else None,
            resync_floors=resync,
            check_room_stats=True)
    finally:
        run_mod.RunState.__init__ = orig
    return result, tw


@pytest.mark.parametrize("seed", IRONCLAD_SEEDS)
@pytest.mark.parametrize("resync", [False, True], ids=["resync-off", "resync-on"])
def test_ironclad_seed_fully_converged(seed, resync):
    """THE hard gate: the full triage predicate, no skips, no xfails."""
    result, tw = _replay(seed, resync)
    v = assess(result, tripwire_bug_sites=tw.bug_sites())
    assert v.clean, "\n".join(v.reasons)


@pytest.mark.parametrize("seed", IRONCLAD_SEEDS)
def test_travelable_points_never_add_unexplained_phantoms(seed):
    """`RunState.travelable_points` (MapTravel.GetTravelablePointsFrom) must
    only ever offer the current point's real pruned-graph children, UNLESS a
    free-travel relic (Winged Boots) is active — in which case the source
    (MapTravel.cs:16-19) offers every point on the next row instead, not a
    union. Any candidate outside `current_point.children` while no relic's
    `should_allow_free_travel()` is true would be a phantom move an RL agent
    or the conformance runner could pick that the real game never offers.

    Regression for an investigation that first looked like a phantom-move
    bug: at 89U21BV1TZ act-0 floor 2, the sim offers 2 map candidates where
    `run.map.grid`'s pruned edges show only 1 child of the current point.
    That candidate is real, though — the save (`map_history[0][0]
    .player_stats[].relic_choices`) confirms this seed's Neow pick was
    Winged Boots, so the extra candidate is the free-travel row, exactly
    matching `MapTravel.GetTravelablePointsFrom`. This test drives the full
    replay and asserts NO candidate is unexplained by that rule, for every
    map decision in both hard-gated seeds."""
    import sts2_rl.run as run_mod

    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")

    orig_enter_point = run_mod.RunState.enter_point
    unexplained: list[str] = []

    def patched(self, dest):
        points = self.travelable_points()
        children = set(self.current_point.children)
        extra = [p for p in points if p not in children]
        if extra and not any(r.should_allow_free_travel() for r in self.relics):
            unexplained.append(
                f"{self.current_point}: unexplained extra candidates {extra}"
            )
        return orig_enter_point(self, dest)

    run_mod.RunState.enter_point = patched
    try:
        ReplayRunner(rec, oracle).run(stop_after_act=2)
    finally:
        run_mod.RunState.enter_point = orig_enter_point

    assert not unexplained, "\n".join(unexplained)
