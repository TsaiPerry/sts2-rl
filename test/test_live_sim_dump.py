"""Task 15 (SpireBot live bot): the sim-side obs dump's tests.

``sts2_rl/live/sim_obs_dump.py`` drives a recorded conformance run through
the parity sim (the SAME full-combat-replay path the hard-convergence gates
use — ``sts2_rl.conformance.runner.ReplayRunner`` — not a force-win stub)
and emits one JSON line per decision point, for Task 16's offline sim/game
join against the C# ``DecisionDumper`` output (join key: ``(floor, kind,
decision_index)``).

Smoke-only: driving a whole 49-floor run is slow, so most assertions here
use ``stop_after_act=0`` (act 0 only, ~18 floors) via the internal
``dump_seed`` argument — the CLI itself always drives the full run (asserted
separately, not exercised end-to-end by the fast tests).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[1] / ".." / "RunReplays" / "RunReplays" / "Resources"
REC = REC.resolve()
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

SEED = "89U21BV1TZ"


def _dump(tmp_path, seed=SEED, stop_after_act=0):
    from sts2_rl.live.sim_obs_dump import dump_seed

    out = tmp_path / "sim_dump.jsonl"
    n = dump_seed(seed, out, stop_after_act=stop_after_act)
    lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    return n, lines


def test_dump_emits_more_than_zero_lines(tmp_path):
    n, lines = _dump(tmp_path)
    assert n > 0
    assert len(lines) == n


def test_dump_lines_have_contract_dims(tmp_path):
    from sts2_rl import run_env

    layout = run_env.run_obs_layout()
    _, lines = _dump(tmp_path)
    assert lines
    for rec in lines:
        assert len(rec["f"]) == layout.f_dim
        assert len(rec["i"]) == layout.i_dim


def test_dump_lines_have_required_fields(tmp_path):
    _, lines = _dump(tmp_path)
    for rec in lines:
        assert set(rec) == {"act", "floor", "kind", "decision_index", "f", "i"}
        assert isinstance(rec["act"], int)
        assert isinstance(rec["floor"], int)
        assert isinstance(rec["kind"], str)
        assert isinstance(rec["decision_index"], int)


def test_dump_act_is_zero_for_act_one_decisions(tmp_path):
    """stop_after_act=0 drives only act 0 (the game's "act 1"), so every
    emitted line's 0-based `act` field must be 0."""
    _, lines = _dump(tmp_path, stop_after_act=0)
    assert lines
    assert all(rec["act"] == 0 for rec in lines)


def test_decision_index_resets_per_act(tmp_path):
    """The same (floor, kind) pair recurring in two different acts must get
    independent decision_index counters, each starting at 0 — the join key
    is (act, floor, kind, decision_index), not (floor, kind, decision_index)."""
    _, lines = _dump(tmp_path, stop_after_act=1)
    acts_seen = {rec["act"] for rec in lines}
    assert acts_seen >= {0, 1}, "need decisions from at least two acts to test the reset"

    seen: dict[tuple[int, int, str], int] = {}
    for rec in lines:
        key = (rec["act"], rec["floor"], rec["kind"])
        expected = seen.get(key, 0)
        assert rec["decision_index"] == expected, (
            f"{key}: expected decision_index {expected}, got {rec['decision_index']}"
        )
        seen[key] = expected + 1


def test_dump_floats_all_finite(tmp_path):
    _, lines = _dump(tmp_path)
    for rec in lines:
        assert all(math.isfinite(x) for x in rec["f"])
        assert all(math.isfinite(x) for x in rec["i"])


def test_dump_kind_vocabulary_matches_csharp_names(tmp_path):
    """kind strings must be drawn from the C# DecisionKind names (mirrored
    as closely as the sim's taxonomy allows — see the module docstring's
    mapping table), not the sim's own lowercase DecisionKind.value strings."""
    _, lines = _dump(tmp_path)
    seen = {rec["kind"] for rec in lines}
    allowed = {"Combat", "Map", "Event", "Shop", "Rest", "RewardScreen",
               "SelectCards", "SelectOption"}
    assert seen <= allowed
    assert seen  # at least one kind actually fired


def test_decision_index_resets_per_floor_and_kind(tmp_path):
    """decision_index is a running counter per (floor, kind), starting at 0,
    incrementing by exactly 1 each time that exact pair recurs."""
    _, lines = _dump(tmp_path)
    seen: dict[tuple[int, str], int] = {}
    for rec in lines:
        key = (rec["floor"], rec["kind"])
        expected = seen.get(key, 0)
        assert rec["decision_index"] == expected, (
            f"{key}: expected decision_index {expected}, got {rec['decision_index']}"
        )
        seen[key] = expected + 1


def test_dump_includes_combat_decisions(tmp_path):
    """Act 0 of 89U21BV1TZ has annotated (fully replayed) combats, so at
    least one Combat-kind decision must appear."""
    _, lines = _dump(tmp_path)
    assert any(rec["kind"] == "Combat" for rec in lines)


def test_dump_includes_map_decisions(tmp_path):
    _, lines = _dump(tmp_path)
    assert any(rec["kind"] == "Map" for rec in lines)


def test_dump_is_deterministic_across_runs(tmp_path):
    """Same recording, driven twice, must produce byte-identical dumps —
    the whole point of replaying a recorded command stream rather than an
    unseeded live policy."""
    _, lines1 = _dump(tmp_path, stop_after_act=0)
    out2 = tmp_path / "sim_dump2.jsonl"
    from sts2_rl.live.sim_obs_dump import dump_seed
    dump_seed(SEED, out2, stop_after_act=0)
    lines2 = [json.loads(l) for l in out2.read_text().splitlines() if l.strip()]
    assert lines1 == lines2


def test_cli_smoke(tmp_path):
    """The CLI module wraps dump_seed with an argparse front end; run it
    in-process (importable main()) against a single act for speed."""
    import sys

    from sts2_rl.live import sim_obs_dump

    out = tmp_path / "cli_dump.jsonl"
    argv = ["--seed", SEED, "--out", str(out), "--stop-after-act", "0"]
    sim_obs_dump.main(argv)
    assert out.exists()
    lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert lines
