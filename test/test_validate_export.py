"""Unit tests for tools/validate_export.py (the sim-side predicted-vs-realized
diff of the RunReplays autoplay dump). tools/ is not a package, so load the
module by path; the tests build tiny in-memory replay/JSONL/result fixtures so
they don't depend on the RunReplays recordings being present."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_export.py"
_spec = importlib.util.spec_from_file_location("validate_export", _MOD_PATH)
ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve)

_HEADER = (
    "# Character: IRONCLAD\n# Seed: TEST000000\n# Ascension: 0\n"
    "# Acts: ACT.OVERGROWTH\n# Game: v0\n# Mod: 0\n"
)

# Two play commands + an end turn; command 0 and 1 carry Hand/Enemies annotations.
_BODY = (
    "PlayCard 0 # CARD.STRIKE_IRONCLAD (1) || Hand: [Strike, Defend] "
    "Enemies: [Wurm 40/40]\n"
    "PlayCard 1 1 # CARD.DEFEND_IRONCLAD (2) || Hand: [Defend] Enemies: [Wurm 34/40]\n"
    "EndTurn # turn 1\n"
)


def _write(path: Path, body: str) -> Path:
    path.write_text(_HEADER + body, encoding="utf-8")
    return path


def _snaps_matching() -> list[dict]:
    """JSONL whose Enemies agree with _BODY's text annotations (hand as ids)."""
    return [
        {"Floor": 1, "Hand": [{"Id": "CARD.STRIKE"}, {"Id": "CARD.DEFEND"}],
         "Enemies": [{"Name": "Wurm", "CurrentHp": 40, "MaxHp": 40}]},
        {"Floor": 1, "Hand": [{"Id": "CARD.DEFEND"}],
         "Enemies": [{"Name": "Wurm", "CurrentHp": 34, "MaxHp": 40}]},
        {"Floor": 1},  # EndTurn: no combat annotation
    ]


def _make_dir(tmp_path: Path, realized_body: str, snaps, result: dict) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    _write(out / "replayed.sts2replay", realized_body)
    (out / "annotations.jsonl").write_text(
        "\n".join(json.dumps(s) for s in snaps) + "\n", encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return out


def test_identical_matches(tmp_path):
    predicted = _write(tmp_path / "predicted.sts2replay", _BODY)
    out = _make_dir(tmp_path, _BODY, _snaps_matching(),
                    {"stalled": False, "commandsConsumed": 3, "lastFloor": 1})
    rc = ve.main(predicted, out / "replayed.sts2replay",
                 out / "annotations.jsonl", out / "result.json")
    assert rc == 0


def test_hand_and_enemy_divergence(tmp_path):
    predicted = ve.parse_recording(_write(tmp_path / "p.sts2replay", _BODY))
    realized_body = _BODY.replace("34/40", "99/40").replace("Hand: [Defend]",
                                                            "Hand: [Block]")
    realized = ve.parse_recording(_write(tmp_path / "r.sts2replay", realized_body))
    divs = ve.diff_annotations(predicted, realized)
    streams = {d.stream for d in divs}
    assert "hand" in streams and "enemies" in streams
    # both land on command index 1 (the mutated line)
    assert all(d.command_index == 1 for d in divs)


def test_early_stall_is_count_divergence(tmp_path):
    predicted = ve.parse_recording(_write(tmp_path / "p.sts2replay", _BODY))
    # realized truncated to the first command only
    truncated = "PlayCard 0 # CARD.STRIKE_IRONCLAD (1) || Hand: [Strike, Defend] " \
                "Enemies: [Wurm 40/40]\n"
    realized = ve.parse_recording(_write(tmp_path / "r.sts2replay", truncated))
    divs = ve.diff_annotations(predicted, realized)
    counts = [d for d in divs if d.stream == "count"]
    assert len(counts) == 1 and counts[0].expected == 3 and counts[0].actual == 1


def test_command_desync_stops_diff(tmp_path):
    predicted = ve.parse_recording(_write(tmp_path / "p.sts2replay", _BODY))
    # swap command 1 to a different action -> stream desync at index 1
    desynced = _BODY.replace("PlayCard 1 1 # CARD.DEFEND_IRONCLAD (2)",
                             "UsePotion 0 # something")
    realized = ve.parse_recording(_write(tmp_path / "r.sts2replay", desynced))
    divs = ve.diff_annotations(predicted, realized)
    cmd_divs = [d for d in divs if d.stream == "command"]
    assert len(cmd_divs) == 1 and cmd_divs[0].command_index == 1


def test_jsonl_crosscheck_flags_mod_dump_bug(tmp_path):
    realized = ve.parse_recording(_write(tmp_path / "r.sts2replay", _BODY))
    bad = _snaps_matching()
    bad[0]["Enemies"][0]["CurrentHp"] = 40  # text says 40 -> agree
    bad[1]["Enemies"][0]["CurrentHp"] = 1   # text says 34 -> DISAGREE
    divs = ve.crosscheck_jsonl(realized, bad)
    assert any(d.stream == "jsonl.enemies" and d.command_index == 1 for d in divs)


def test_stall_forces_nonzero_exit(tmp_path):
    predicted = _write(tmp_path / "predicted.sts2replay", _BODY)
    out = _make_dir(tmp_path, _BODY, _snaps_matching(),
                    {"stalled": True, "stallReason": "hung", "commandsConsumed": 3})
    rc = ve.main(predicted, out / "replayed.sts2replay",
                 out / "annotations.jsonl", out / "result.json")
    assert rc == 1  # annotations match but the stall flag alone fails the run
