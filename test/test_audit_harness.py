"""Tests for the audit completeness harness (tools/audit/harness.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.audit import harness

FIXTURE_CS = """\
using System;
namespace MegaCrit.Sts2.Core.Models.Relics;

public sealed class FixtureRelic : RelicModel
{
    public override RelicRarity Rarity => RelicRarity.Rare;

    public override Task BeforeCombatStart()
    {
        return Task.CompletedTask;
    }

    public override Task AfterDamageReceivedEarly(Creature target, decimal amount)
    {
        return Task.CompletedTask;
    }

    public override decimal ModifyPowerAmountGivenMultiplicative(PowerModel power, Creature giver, decimal amount, Creature? target, CardModel? cardSource)
    {
        return 1m;
    }

    private void Helper() { }
}
"""


class TestListOverrides:
    def test_names_in_declaration_order(self):
        assert harness.list_overrides(FIXTURE_CS) == [
            "Rarity",
            "BeforeCombatStart",
            "AfterDamageReceivedEarly",
            "ModifyPowerAmountGivenMultiplicative",
        ]

    def test_ignores_non_override_members(self):
        assert "Helper" not in harness.list_overrides(FIXTURE_CS)


class TestHashing:
    def test_sha256_normalizes_line_endings(self, tmp_path):
        a = tmp_path / "a.cs"
        b = tmp_path / "b.cs"
        a.write_bytes(b"x\r\ny\r\n")
        b.write_bytes(b"x\ny\n")
        assert harness.file_sha256(a) == harness.file_sha256(b)


class TestNaming:
    def test_pascal(self):
        assert harness._pascal("unsettling_lamp") == "UnsettlingLamp"
        assert harness._pascal("twig_slime_m") == "TwigSlimeM"

    def test_snake_round_trips(self):
        assert harness._snake("TwigSlimeM") == "twig_slime_m"
        assert harness._pascal(harness._snake("UnsettlingLamp")) == "UnsettlingLamp"


class TestRoster:
    def test_relic_roster_includes_unsettling_lamp(self):
        rows = harness.roster("relic")
        row = next(r for r in rows if r["unit"] == "relic/unsettling_lamp")
        assert row["game_exists"] is True
        assert row["sim_path"].replace("\\", "/").endswith("relics/unsettling_lamp.py")

    def test_monster_roster_nonempty_and_snake_ids(self):
        rows = harness.roster("monster")
        assert rows, "monster roster should not be empty"
        assert all(r["unit"].startswith("monster/") for r in rows)

    def test_unported_returns_cs_filenames(self):
        names = harness.unported("relic")
        assert all(n.endswith(".cs") for n in names)

    @pytest.mark.parametrize("kind", sorted(harness.GAME_MODEL_DIRS))
    def test_roster_rows_have_expected_shape_for_all_kinds(self, kind):
        rows = harness.roster(kind)
        assert rows, f"{kind} roster should not be empty"
        for row in rows:
            assert set(row.keys()) == {
                "unit", "sim_path", "game_path", "game_exists",
            }


class TestInterfaceContract:
    """Pins the module-level names later tasks consume verbatim."""

    def test_game_model_dirs_keys(self):
        assert set(harness.GAME_MODEL_DIRS) == {
            "relic", "power", "card", "monster", "event", "enchantment",
        }

    def test_verdicts_order(self):
        assert harness.VERDICTS == (
            "faithful", "waiver", "deliberate-divergence", "gap",
        )


def _valid_record(harness, tmp_path):
    """A minimal valid content record against a fixture C# file."""
    cs = tmp_path / "FixtureRelic.cs"
    cs.write_text(FIXTURE_CS, encoding="utf-8")
    return {
        "unit": "relic/fixture_relic",
        "game_source": {"path": "FixtureRelic.cs", "sha256": harness.file_sha256(cs)},
        "sim_source": {"path": "sts2_rl/relics/unsettling_lamp.py",
                       "sha256": "0" * 64},
        "hooks": {
            "Rarity": {"maps_to": "rarity", "verdict": "faithful"},
            "BeforeCombatStart": {"maps_to": "on_combat_start", "verdict": "faithful"},
            "AfterDamageReceivedEarly": {
                "maps_to": "", "verdict": "waiver",
                "rationale": "Early hook phases not modeled"},
            "ModifyPowerAmountGivenMultiplicative": {
                "maps_to": "modify_power_amount", "verdict": "faithful"},
        },
        "guards": [],
        "verdict": "waiver",
        "audited": "2026-07-24",
    }


class TestValidateRecord:
    def test_valid_record_passes(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_missing_hook_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        del rec["hooks"]["BeforeCombatStart"]
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("BeforeCombatStart" in e for e in errs)

    def test_bad_verdict_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["hooks"]["Rarity"]["verdict"] = "fine"
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("fine" in e for e in errs)

    def test_waiver_without_rationale_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["hooks"]["AfterDamageReceivedEarly"]["rationale"] = ""
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("rationale" in e for e in errs)

    def test_gap_without_issue_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["guards"] = [{"what": "power.IsVisible", "verdict": "gap"}]
        rec["verdict"] = "gap"
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("issue" in e for e in errs)

    def test_wrong_rollup_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["verdict"] = "faithful"  # but AfterDamageReceivedEarly is a waiver
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("rollup" in e for e in errs)

    def test_faithful_without_maps_to_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["hooks"]["Rarity"]["maps_to"] = ""
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("maps_to" in e for e in errs)

    def test_bad_audited_format_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["audited"] = "07/24/2026"
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("audited" in e for e in errs)

    def test_empty_audited_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["audited"] = ""
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("audited" in e for e in errs)

    def test_deliberate_divergence_without_rationale_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["hooks"]["BeforeCombatStart"]["verdict"] = "deliberate-divergence"
        rec["verdict"] = "deliberate-divergence"
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("rationale" in e for e in errs)

    def test_game_source_not_found_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["game_source"]["path"] = "DoesNotExist.cs"
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("game source not found" in e for e in errs)

    def test_seam_record_requires_steps(self, tmp_path):
        rec = {
            "unit": "seam/damage_pipeline",
            "game_sources": [{"path": "FixtureRelic.cs", "sha256": "0" * 64}],
            "sim_sources": [{"path": "sts2_rl/cmds.py", "sha256": "0" * 64}],
            "steps": [],
            "guards": [],
            "verdict": "faithful",
            "audited": "2026-07-24",
        }
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("steps" in e for e in errs)


class TestSkeleton:
    def test_skeleton_lists_every_override(self, tmp_path):
        (tmp_path / "src/Core/Models/Relics").mkdir(parents=True)
        (tmp_path / "src/Core/Models/Relics/UnsettlingLamp.cs").write_text(
            FIXTURE_CS, encoding="utf-8")
        out = harness.skeleton("relic/unsettling_lamp",
                               game_root=tmp_path,
                               audits_dir=tmp_path / "audits")
        rec = json.loads(out.read_text(encoding="utf-8"))
        assert set(rec["hooks"]) == {
            "Rarity", "BeforeCombatStart", "AfterDamageReceivedEarly",
            "ModifyPowerAmountGivenMultiplicative",
        }
        assert rec["verdict"] == ""
        assert rec["game_source"]["sha256"]
        assert rec["sim_source"]["sha256"]
