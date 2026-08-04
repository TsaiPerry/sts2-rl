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


def test_sim_only_record_counts_as_audited(tmp_path, monkeypatch):
    """A sim-only unit has no C# file, so the ordinary shape left it in
    `unaudited` forever and staleness had nothing to check."""
    audits = _setup(tmp_path)
    monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: [{
        "unit": "relic/fixture_relic",
        "sim_path": "sts2_rl/relics/unsettling_lamp.py",
        "game_path": "src/Core/Models/Relics/Nope.cs",
        "game_exists": False,
    }])
    sim_path = "sts2_rl/relics/unsettling_lamp.py"
    rec = {
        "unit": "relic/fixture_relic",
        "sim_only": True,
        "rationale": "sim-only fixture, no C# counterpart",
        "sim_source": {"path": sim_path,
                       "sha256": harness.file_sha256(Path(sim_path))},
        "hooks": {},
        "guards": [],
        "verdict": "waiver",
        "audited": "2026-07-26",
    }
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["audited"] == 1
    assert out["relic"]["unaudited"] == []
    assert out["relic"]["invalid"] == 0
    assert out["relic"]["stale"] == 0

    rec["sim_source"]["sha256"] = "0" * 64
    _write(audits, rec)
    out = audit_status.collect(kinds=("relic",), game_root=tmp_path,
                               audits_dir=audits)
    assert out["relic"]["stale"] == 1


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


class TestQueueGeneratorCoversEveryKind:
    """`gap_queue.py` keeps its own kind list, and that list can silently omit
    a completed tier.

    It did. `potion` became a roster kind in `harness.GAME_MODEL_DIRS` on
    2026-07-26 and 51 finished records landed on 2026-07-27, and for that whole
    window `py audit/tools/gap_queue.py counts` printed
    `NOT AUDITED : potion (51 C# units)` and left 152 gap entries out of
    `audit/GAP-QUEUE.md` -- while `audit_status.py`, which derives its kinds
    from the harness, reported the same records audited. Two tools, two answers,
    and only the one nobody was reading was right.

    These assertions are the cheap fix: the queue generator must account for
    every kind the harness defines, either as audited or as explicitly
    unaudited.
    """

    def test_every_harness_kind_is_known_to_the_queue_generator(self):
        from audit.tools import gap_queue

        harness_kinds = set(harness.GAME_MODEL_DIRS)
        known = set(gap_queue.CONTENT_KINDS) | set(gap_queue.UNAUDITED_KINDS)
        assert harness_kinds - known == set(), (
            "gap_queue.py does not know about these kinds, so their records "
            "are invisible to GAP-QUEUE.md: "
            f"{sorted(harness_kinds - known)}"
        )

    def test_the_queue_generator_invents_no_kind(self):
        from audit.tools import gap_queue

        known = set(gap_queue.CONTENT_KINDS) | set(gap_queue.UNAUDITED_KINDS)
        assert known - set(harness.GAME_MODEL_DIRS) == set()

    def test_a_kind_is_audited_or_unaudited_but_not_both(self):
        from audit.tools import gap_queue

        assert not (set(gap_queue.CONTENT_KINDS)
                    & set(gap_queue.UNAUDITED_KINDS))

    def test_a_kind_with_records_is_not_listed_unaudited(self):
        """The specific shape of the 2026-07-26 defect: records on disk while
        the generator calls the kind unaudited."""
        from audit.tools import gap_queue

        wrong = [
            kind for kind in gap_queue.UNAUDITED_KINDS
            if (gap_queue.RECORDS / kind).is_dir()
            and any((gap_queue.RECORDS / kind).glob("*.json"))
        ]
        assert wrong == [], (
            f"these kinds have records but gap_queue reports them NOT AUDITED: "
            f"{wrong}"
        )


class TestQueueGeneratorCoversEverySeamWithGaps:
    """`gap_queue.py` keeps a SECOND hand-maintained list -- `SEAMS` -- and it
    has the identical failure mode as the kind list above.

    `SEAMS` is deliberately NOT `harness.SEAMS`: a seam is added the moment it
    has its first `verdict: "gap"` entry to extract, not the moment its record
    is created, because a freshly wired seam ships an empty `steps: []`
    scaffold with nothing to extract and some of the names are common enough
    English words ("rewards") to false-positive against an unrelated xfail
    reason at the pin locator.

    That rule is correct and the comment states it. What was missing is anything
    that ENFORCES it. On 2026-08-03 the systems-tier campaign wired six seams,
    then filed 12 gap entries across four of them -- and `counts` went on
    reporting `seam ... 0 live entries`, because the list still named the
    original six. Same shape as the `potion` omission the class above exists
    for: two tools, two answers, and only the one nobody was reading was right.

    This is the enforcement. The rule is not "SEAMS == harness.SEAMS"; it is
    "every seam record that has something to extract is in SEAMS".
    """

    def _seam_records_with_gap_entries(self):
        import json

        from audit.tools import gap_queue

        out = []
        for path in sorted(gap_queue.RECORD_DIR.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            entries = record.get("steps", []) + record.get("guards", [])
            if any(e.get("verdict") == "gap" for e in entries):
                out.append(path.stem)
        return out

    def test_every_seam_with_a_gap_entry_is_extracted(self):
        from audit.tools import gap_queue

        missing = [s for s in self._seam_records_with_gap_entries()
                   if s not in gap_queue.SEAMS]
        assert missing == [], (
            "these seam records carry `verdict: \"gap\"` entries that "
            "gap_queue.py never extracts, so they are invisible to "
            f"`counts`, `coverage` and GAP-QUEUE.md: {missing}"
        )

    def test_the_queue_generator_invents_no_seam(self):
        from audit.tools import gap_queue

        assert set(gap_queue.SEAMS) - set(harness.SEAMS) == set()


class TestTypedLivenessIsHonouredEverywhere:
    """The typed ``"live"`` key must outrank the prose scan in EVERY record
    shape, not just the one it was added for.

    It did not. ``live`` arrived on 2026-07-27 with the monster tier -- a
    *content* kind -- and only the content branch of ``gap_queue.extract`` was
    taught to pass it. The six *seam* records went on being labelled by
    ``_liveness``'s caps-token scan, so a seam entry that said ``"live": false``
    in typed data was still reported ``unlabelled``.

    Round 11 found it the way this project always finds tooling defects: by unit
    work, never by tool review. Two batches settled 21 seam entries, wrote the
    key, validated their records clean -- and ``counts`` refused to move. The
    records were right and the tool was wrong, which is the failure direction
    that costs the most, because the tool is what everyone downstream reads.
    """

    def _seam_gap_entries_with_typed_live(self):
        import json

        from audit.tools import gap_queue

        out = {}
        for seam in gap_queue.SEAMS:
            path = gap_queue.RECORDS / "seam" / f"{seam}.json"
            rec = json.loads(path.read_text(encoding="utf-8"))
            for section in ("steps", "guards"):
                for i, e in enumerate(rec.get(section, [])):
                    if e.get("verdict") != "gap" or "live" not in e:
                        continue
                    eid = gap_queue._entry_id(section, e["what"], i)
                    out[f"{seam}/{eid}"] = e["live"]
        return out

    def test_a_seam_records_typed_live_key_reaches_the_queue(self):
        from audit.tools import gap_queue

        typed = self._seam_gap_entries_with_typed_live()
        assert typed, (
            "no seam gap entry carries a typed 'live' key, so this test proves "
            "nothing -- it is asserting over an empty set"
        )
        reported = {e["id"]: e["liveness"] for e in gap_queue.extract()}
        wrong = {
            eid: (want, reported.get(eid))
            for eid, want in typed.items()
            if reported.get(eid) != ("live" if want else "dormant")
        }
        assert wrong == {}, (
            "these seam entries state their liveness in typed data and the "
            f"queue reports something else (id: expected, got): {wrong}"
        )


class TestPinsResolveToAMechanism:
    """A strict xfail pin that anchors no mechanism is invisible non-coverage.

    `gap_queue.pins()` derived a mechanism only from the six seam names until
    2026-07-27, so the project's first content-anchored pins resolved to a
    mechanism literally named `None/G1` -- counted in `strict xfail pins` while
    pinning nothing, and leaving the LIVE mechanism they prove reported as
    `unpinned`.
    """

    def test_every_pin_resolves(self):
        from audit.tools import gap_queue

        entries = gap_queue.extract()
        by_key, by_record = {}, {}
        for e in entries:
            by_key.setdefault(e["id"], e["mechanism"])
            by_record.setdefault(e["record"], {})[e["local_id"]] = (
                e["mechanism"], e["what"])
        unresolved = [
            p["test"] for p in gap_queue.pins()
            if not gap_queue.pin_mechanisms(p, by_key, by_record)
        ]
        assert unresolved == [], (
            "these pins are counted as pins but anchor no mechanism: "
            f"{unresolved}"
        )

    def test_no_pin_resolves_to_a_mechanism_with_no_entries(self):
        from audit.tools import gap_queue

        entries = gap_queue.extract()
        known = {e["mechanism"] for e in entries}
        by_key, by_record = {}, {}
        for e in entries:
            by_key.setdefault(e["id"], e["mechanism"])
            by_record.setdefault(e["record"], {})[e["local_id"]] = (
                e["mechanism"], e["what"])
        bogus = {
            m
            for p in gap_queue.pins()
            for m in gap_queue.pin_mechanisms(p, by_key, by_record)
            if m not in known
        }
        assert bogus == set(), f"pins name unknown mechanisms: {sorted(bogus)}"
