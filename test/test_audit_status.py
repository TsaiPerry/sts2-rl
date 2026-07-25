"""Tests for tools/audit_status.py using a synthetic game root + ledger.

Self-contained on purpose: `test/` shadows CPython's stdlib `test` package,
so importing fixtures from test.test_audit_harness would resolve to the
stdlib and fail — the fixture C# text is duplicated here instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools import audit_status
from tools.audit import harness

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
