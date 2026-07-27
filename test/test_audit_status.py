"""Tests for audit/tools/audit_status.py using a synthetic game root + ledger.

Self-contained on purpose: `test/` shadows CPython's stdlib `test` package,
so importing fixtures from test.test_audit_harness would resolve to the
stdlib and fail — the fixture C# text is duplicated here instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from audit.tools import audit_status
from audit.tools import harness

FIXTURE_CS = """\
public sealed class FixtureRelic : RelicModel
{
    public override RelicRarity Rarity => RelicRarity.Rare;

    public override Task BeforeCombatStart()
    {
        return Task.CompletedTask;
    }
}
"""


def _setup(tmp_path):
    """Synthetic game root with one relic file + audits dir."""
    (tmp_path / "src/Core/Models/Relics").mkdir(parents=True)
    (tmp_path / "src/Core/Models/Relics/FixtureRelic.cs").write_text(
        FIXTURE_CS, encoding="utf-8")
    audits = tmp_path / "audits"
    (audits / "relic").mkdir(parents=True)
    return audits


def _make_record(tmp_path):
    """A valid, non-stale record for the synthetic FixtureRelic."""
    return {
        "unit": "relic/fixture_relic",
        "game_source": {
            "path": "src/Core/Models/Relics/FixtureRelic.cs",
            "sha256": harness.file_sha256(
                tmp_path / "src/Core/Models/Relics/FixtureRelic.cs"),
        },
        "sim_source": {
            "path": "sts2_rl/relics/unsettling_lamp.py",
            "sha256": harness.file_sha256(
                Path("sts2_rl/relics/unsettling_lamp.py")),
        },
        "hooks": {
            "Rarity": {"maps_to": "rarity", "verdict": "faithful"},
            "BeforeCombatStart": {"maps_to": "on_combat_start",
                                  "verdict": "faithful"},
        },
        "guards": [],
        "verdict": "faithful",
        "audited": "2026-07-24",
    }


def _write(audits, rec):
    (audits / "relic" / "fixture_relic.json").write_text(
        json.dumps(rec), encoding="utf-8")


def _fixture_rows():
    return [{
        "unit": "relic/fixture_relic",
        "sim_path": "sts2_rl/relics/unsettling_lamp.py",
        "game_path": "src/Core/Models/Relics/FixtureRelic.cs",
        "game_exists": True,
    }]


def test_counts_audited_and_unaudited(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    _write(audits, _make_record(tmp_path))
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["total"] == 1
    assert out["relic"]["audited"] == 1
    assert out["relic"]["unaudited"] == []
    assert out["relic"]["stale"] == 0


def test_hash_drift_is_stale(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    rec = _make_record(tmp_path)
    rec["game_source"]["sha256"] = "0" * 64  # stale
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["stale"] == 1


def test_extra_sources_drift_is_stale(tmp_path, monkeypatch):
    """A content record's citations beyond its own two files are pinned by
    `extra_sources`; drift in one of them must mark the record stale."""
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    extra_cs = tmp_path / "src/Core/Commands/PowerCmd.cs"
    extra_cs.parent.mkdir(parents=True, exist_ok=True)
    extra_cs.write_text("public static class PowerCmd {}\n", encoding="utf-8")

    rec = _make_record(tmp_path)
    rec["extra_sources"] = [
        {"path": "src/Core/Commands/PowerCmd.cs",
         "sha256": harness.file_sha256(extra_cs), "side": "game"},
        {"path": "sts2_rl/cmds.py",
         "sha256": harness.file_sha256(Path("sts2_rl/cmds.py")), "side": "sim"},
    ]
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["audited"] == 1
    assert out["relic"]["stale"] == 0

    # Drift the game-side extra source only: the singular pair is untouched,
    # so the pre-fix _is_stale reported 0 here.
    rec["extra_sources"][0]["sha256"] = "0" * 64
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["stale"] == 1

    # And the sim-side one, resolved against the repo root rather than the
    # game root.
    rec["extra_sources"][0]["sha256"] = harness.file_sha256(extra_cs)
    rec["extra_sources"][1]["sha256"] = "0" * 64
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["stale"] == 1


def test_extra_sources_missing_file_is_stale(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    rec = _make_record(tmp_path)
    rec["extra_sources"] = [
        {"path": "src/Core/Gone.cs", "sha256": "0" * 64, "side": "game"}]
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["stale"] == 1


def test_gap_counted(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    rec = _make_record(tmp_path)
    rec["guards"] = [{"what": "power.IsVisible", "verdict": "gap",
                      "issue": "not modeled"}]
    rec["verdict"] = "gap"
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["gaps"] == 1


def test_live_column_counts_records_with_a_live_gap(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    rec = _make_record(tmp_path)
    rec["guards"] = [{"what": "g", "verdict": "gap", "issue": "x"}]
    rec["verdict"] = "gap"
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["gaps"] == 1
    assert out["relic"]["live"] == 0     # liveness not stated

    rec["guards"][0]["live"] = False
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["live"] == 0     # stated dormant

    rec["guards"][0]["live"] = True
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["gaps"] == 1
    assert out["relic"]["live"] == 1


def test_malformed_json_is_invalid(tmp_path, monkeypatch):
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    (audits / "relic" / "fixture_relic.json").write_text(
        "{not valid json", encoding="utf-8")
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["invalid"] == 1

    monkeypatch.setattr(harness, "DEFAULT_GAME_ROOT", tmp_path)
    monkeypatch.setattr(harness, "DEFAULT_AUDITS_DIR", audits)
    assert audit_status.main(["--kind", "relic"]) == 2


def test_unit_mismatch_is_invalid(tmp_path, monkeypatch):
    """A record filed under relic/fixture_relic.json but claiming a
    different unit must not be trusted for staleness checking — it should
    be flagged invalid instead."""
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    rec = _make_record(tmp_path)
    rec["unit"] = "relic/some_other_relic"
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["invalid"] == 1
    assert out["relic"]["audited"] == 0


def test_seam_shape_audited_and_stale(tmp_path, monkeypatch):
    """Seam records use the plural game_sources/sim_sources shape; cover
    both the clean-audited case and hash-drift staleness for it."""
    game_file = tmp_path / "src/Core/Commands/FixtureSeam.cs"
    game_file.parent.mkdir(parents=True, exist_ok=True)
    game_file.write_text("public sealed class FixtureSeam {}\n", encoding="utf-8")
    audits = tmp_path / "audits"
    (audits / "seam").mkdir(parents=True)
    monkeypatch.setattr(harness, "SEAMS", ("fixture_seam",))

    sim_path = "sts2_rl/relics/unsettling_lamp.py"
    rec = {
        "unit": "seam/fixture_seam",
        "game_sources": [{
            "path": "src/Core/Commands/FixtureSeam.cs",
            "sha256": harness.file_sha256(game_file),
        }],
        "sim_sources": [{
            "path": sim_path,
            "sha256": harness.file_sha256(Path(sim_path)),
        }],
        "steps": [{"what": "ordering", "verdict": "faithful"}],
        "guards": [],
        "verdict": "faithful",
        "audited": "2026-07-24",
    }
    seam_path = audits / "seam" / "fixture_seam.json"
    seam_path.write_text(json.dumps(rec), encoding="utf-8")

    out = audit_status.collect(kinds=("seam",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["seam"]["total"] == 1
    assert out["seam"]["audited"] == 1
    assert out["seam"]["stale"] == 0

    rec["game_sources"][0]["sha256"] = "0" * 64  # stale
    seam_path.write_text(json.dumps(rec), encoding="utf-8")
    out = audit_status.collect(kinds=("seam",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["seam"]["audited"] == 1
    assert out["seam"]["stale"] == 1


def test_exit_codes(tmp_path, monkeypatch):
    """0 clean; 1 only under --strict with stale/gaps/unaudited; 2 invalid."""
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: _fixture_rows())
    monkeypatch.setattr(harness, "DEFAULT_GAME_ROOT", tmp_path)
    monkeypatch.setattr(harness, "DEFAULT_AUDITS_DIR", audits)

    # Unaudited: default exit 0, strict exit 1.
    assert audit_status.main(["--kind", "relic"]) == 0
    assert audit_status.main(["--kind", "relic", "--strict"]) == 1

    # Valid + current: exit 0 even under strict.
    _write(audits, _make_record(tmp_path))
    assert audit_status.main(["--kind", "relic", "--strict"]) == 0

    # Invalid record: exit 2 regardless of strict.
    rec = _make_record(tmp_path)
    rec["hooks"]["Rarity"]["verdict"] = "nonsense"
    _write(audits, rec)
    assert audit_status.main(["--kind", "relic"]) == 2
