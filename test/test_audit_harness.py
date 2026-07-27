"""Tests for the audit completeness harness (audit/tools/harness.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit.tools import harness

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


FIXTURE_BASE_CS = """\
namespace MegaCrit.Sts2.Core.Models.Powers;

public abstract class FixtureBasePower : PowerModel, ITemporaryPower
{
    public override PowerType Type => PowerType.Buff;

    public override LocString Title => new LocString("x");

    public abstract AbstractModel OriginModel { get; }

    protected virtual bool IsPositive => true;

    public override async Task BeforeApplied(Creature target, decimal amount)
    {
        await Task.CompletedTask;
    }
}
"""

FIXTURE_SUBCLASS_CS = """\
namespace MegaCrit.Sts2.Core.Models.Powers;

public class FixtureSubPower : FixtureBasePower
{
    public override AbstractModel OriginModel => ModelDb.Potion<FlexPotion>();
}
"""

FIXTURE_TUPLE_CS = """\
public sealed class FixtureTuple : PowerModel
{
    public override (PileType, int) ModifyCardPlayResultPileTypeAndPosition(CardModel card, PileType pile, int position)
    {
        return (pile, position);
    }

    public override Task<(bool, decimal)> ResolveThing(Creature target)
    {
        return Task.FromResult((true, 0m));
    }

    public override void PlainVoid(Creature target) { }
}
"""


class TestOverrideEnumeration:
    """Two confirmed blind spots in the enumeration: a return type the regex
    could not parse, and behaviour declared by the base class."""

    def test_tuple_return_types_are_enumerated(self):
        assert harness.list_overrides(FIXTURE_TUPLE_CS) == [
            "ModifyCardPlayResultPileTypeAndPosition",
            "ResolveThing",
            "PlainVoid",
        ]

    def _game_root(self, tmp_path):
        d = tmp_path / "src/Core/Models/Powers"
        d.mkdir(parents=True)
        (d / "FixtureBasePower.cs").write_text(FIXTURE_BASE_CS, encoding="utf-8")
        (d / "FixtureSubPower.cs").write_text(FIXTURE_SUBCLASS_CS, encoding="utf-8")
        harness._cs_index.cache_clear()
        return tmp_path, d / "FixtureSubPower.cs"

    def test_base_class_overrides_are_enumerated(self, tmp_path):
        root, sub = self._game_root(tmp_path)
        text = sub.read_text(encoding="utf-8")
        assert harness.list_overrides(text) == ["OriginModel"]  # text-only
        assert harness.list_overrides(text, game_root=root, source_path=sub) == [
            "OriginModel", "Type", "Title", "BeforeApplied",
        ]

    def test_split_separates_declared_from_inherited(self, tmp_path):
        root, sub = self._game_root(tmp_path)
        declared, inherited = harness.split_overrides(
            sub.read_text(encoding="utf-8"), root, sub)
        assert declared == ["OriginModel"]
        assert inherited == ["Type", "Title", "BeforeApplied"]

    def test_base_may_live_in_another_file(self, tmp_path):
        root, sub = self._game_root(tmp_path)
        found = harness.find_class_file("FixtureBasePower", root)
        assert found is not None and found.name == "FixtureBasePower.cs"
        assert found != sub

    def test_framework_roots_are_not_followed(self, tmp_path):
        """PowerModel & co are the seam tier's scope; following them would add
        the same framework members to all 422 content records."""
        root, _ = self._game_root(tmp_path)
        base = root / "src/Core/Models/Powers/FixtureBasePower.cs"
        _, inherited = harness.split_overrides(
            base.read_text(encoding="utf-8"), root, base)
        assert inherited == []
        assert harness._base_class_name(FIXTURE_BASE_CS) is None

    def test_interface_only_base_list_is_not_followed(self):
        assert harness._base_class_name(
            "public class Foo : IBar\n{\n}\n") is None

    def test_validate_warns_on_un_audited_inherited_override(self, tmp_path):
        root, sub = self._game_root(tmp_path)
        rec = {
            "unit": "power/fixture_sub",
            "game_source": {
                "path": "src/Core/Models/Powers/FixtureSubPower.cs",
                "sha256": harness.file_sha256(sub)},
            "sim_source": {"path": "sts2_rl/powers.py", "sha256": "0" * 64},
            "hooks": {"OriginModel": {"maps_to": "origin", "verdict": "faithful"}},
            "guards": [],
            "verdict": "faithful",
            "audited": "2026-07-26",
        }
        assert harness.validate_record(rec, game_root=root) == []
        assert harness.enumeration_gaps(rec, game_root=root) == [
            "Type", "Title", "BeforeApplied"]
        errs = harness.validate_record(rec, game_root=root,
                                       strict_inherited=True)
        assert any("BeforeApplied" in e for e in errs)

    def test_declared_override_is_still_a_hard_error(self, tmp_path):
        root, sub = self._game_root(tmp_path)
        rec = {
            "unit": "power/fixture_sub",
            "game_source": {
                "path": "src/Core/Models/Powers/FixtureSubPower.cs",
                "sha256": harness.file_sha256(sub)},
            "sim_source": {"path": "sts2_rl/powers.py", "sha256": "0" * 64},
            "hooks": {},
            "guards": [],
            "verdict": "faithful",
            "audited": "2026-07-26",
        }
        errs = harness.validate_record(rec, game_root=root)
        assert any("OriginModel" in e for e in errs)

    def test_skeleton_enumerates_inherited_hooks(self, tmp_path, monkeypatch):
        root, _ = self._game_root(tmp_path)
        monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: [{
            "unit": "power/fixture_sub",
            "sim_path": "sts2_rl/powers.py",
            "game_path": "src/Core/Models/Powers/FixtureSubPower.cs",
            "game_exists": True,
        }])
        out = harness.skeleton("power/fixture_sub", game_root=root,
                               audits_dir=tmp_path / "records")
        rec = json.loads(out.read_text(encoding="utf-8"))
        assert list(rec["hooks"]) == [
            "OriginModel", "Type", "Title", "BeforeApplied"]

    def test_hook_key_reads_the_leading_identifier(self):
        assert harness.hook_key("Type (inherited, Base.cs:32-42)") == "Type"
        assert harness.hook_key("BeforeApplied") == "BeforeApplied"


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


class TestSimOnlyRecord:
    """`card/sweep` has sts2_rl/cards/sweep.py and no Sweep.cs, so the
    ordinary shape could not express it and it read as permanently
    unaudited."""

    def _rec(self, **over):
        rec = {
            "unit": "card/sweep",
            "sim_only": True,
            "rationale": "sim-only test fixture; no Sweep.cs in the game source",
            "sim_source": {"path": "sts2_rl/cards/sweep.py",
                           "sha256": harness.file_sha256(
                               harness._REPO / "sts2_rl/cards/sweep.py")},
            "hooks": {},
            "guards": [],
            "verdict": "waiver",
            "audited": "2026-07-26",
        }
        rec.update(over)
        return rec

    def test_validates_without_a_game_source(self, tmp_path):
        assert harness.validate_record(self._rec(), game_root=tmp_path) == []

    def test_rationale_required(self, tmp_path):
        errs = harness.validate_record(self._rec(rationale=""),
                                       game_root=tmp_path)
        assert any("rationale" in e for e in errs)

    def test_game_source_rejected(self, tmp_path):
        errs = harness.validate_record(
            self._rec(game_source={"path": "X.cs", "sha256": "0" * 64}),
            game_root=tmp_path)
        assert any("must not carry a game_source" in e for e in errs)

    def test_sim_source_must_exist(self, tmp_path):
        errs = harness.validate_record(
            self._rec(sim_source={"path": "sts2_rl/nope.py",
                                  "sha256": "0" * 64}),
            game_root=tmp_path)
        assert any("sim source not found" in e for e in errs)

    def test_verdict_still_required(self, tmp_path):
        errs = harness.validate_record(self._rec(verdict=""),
                                       game_root=tmp_path)
        assert any("verdict" in e for e in errs)

    def test_entries_still_roll_up(self, tmp_path):
        rec = self._rec(
            hooks={"play": {"maps_to": "on_play", "verdict": "faithful"}},
            guards=[{"what": "x", "verdict": "gap", "issue": "y"}],
            verdict="faithful")
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("rollup" in e for e in errs)

    def test_sim_only_false_takes_the_ordinary_path(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["sim_only"] = False
        assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_sim_only_must_be_a_bool(self, tmp_path):
        errs = harness.validate_record(self._rec(sim_only="yes"),
                                       game_root=tmp_path)
        assert any("sim_only must be true" in e for e in errs)

    def test_skeleton_writes_the_sim_only_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr(harness, "roster", lambda kind, game_root=None: [{
            "unit": "card/sweep",
            "sim_path": "sts2_rl/cards/sweep.py",
            "game_path": "src/Core/Models/Cards/Sweep.cs",
            "game_exists": False,
        }])
        out = harness.skeleton("card/sweep", game_root=tmp_path,
                               audits_dir=tmp_path / "records", sim_only=True)
        rec = json.loads(out.read_text(encoding="utf-8"))
        assert rec["sim_only"] is True
        assert "game_source" not in rec
        assert rec["rationale"] == ""      # the agent must supply it
        assert rec["sim_source"]["sha256"]


class TestGapLiveness:
    """`live` turns a LIVE/dormant prose token into data. Optional: gap
    entries written before it existed stay valid."""

    def _gap_rec(self, tmp_path, **extra):
        rec = _valid_record(harness, tmp_path)
        rec["guards"] = [dict({"what": "g", "verdict": "gap",
                               "issue": "not modeled"}, **extra)]
        rec["verdict"] = "gap"
        return rec

    def test_gap_without_the_key_still_validates(self, tmp_path):
        rec = self._gap_rec(tmp_path)
        assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_live_true_and_false_accepted(self, tmp_path):
        for value in (True, False):
            rec = self._gap_rec(tmp_path, live=value)
            assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_non_boolean_live_rejected(self, tmp_path):
        rec = self._gap_rec(tmp_path, live="LIVE")
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("'live' must be true or false" in e for e in errs)

    def test_live_on_a_non_gap_entry_rejected(self, tmp_path):
        """Silently ignoring it would be worse: the record would look
        annotated and never be counted."""
        rec = _valid_record(harness, tmp_path)
        rec["hooks"]["Rarity"]["live"] = True
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("only means something on a 'gap'" in e for e in errs)

    def test_record_entries_covers_all_three_sections(self):
        rec = {"hooks": {"A": {"verdict": "gap"}},
               "steps": [{"verdict": "faithful"}],
               "guards": [{"verdict": "waiver"}]}
        assert len(harness.record_entries(rec)) == 3
        assert harness.record_entries({}) == []


class TestExtraSources:
    """The optional `extra_sources` list: the files a content record's
    verdicts cite beyond the unit's own two. Optional by design — the 422
    records written before it existed must stay valid."""

    def test_record_without_the_key_still_validates(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        assert "extra_sources" not in rec
        assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_well_formed_entries_accepted(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = [
            {"path": "FixtureRelic.cs", "sha256": "a" * 64, "side": "game"},
            {"path": "sts2_rl/cmds.py", "sha256": "b" * 64, "side": "sim"},
        ]
        assert harness.validate_record(rec, game_root=tmp_path) == []

    def test_missing_side_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = [{"path": "FixtureRelic.cs", "sha256": "a" * 64}]
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("side" in e for e in errs)

    def test_bad_side_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = [
            {"path": "x.cs", "sha256": "a" * 64, "side": "elsewhere"}]
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("elsewhere" in e for e in errs)

    def test_missing_sha_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = [{"path": "x.cs", "side": "game"}]
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("sha256" in e for e in errs)

    def test_non_hex_sha_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = [
            {"path": "x.cs", "sha256": "not-a-hash", "side": "game"}]
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("hex" in e for e in errs)

    def test_non_list_rejected(self, tmp_path):
        rec = _valid_record(harness, tmp_path)
        rec["extra_sources"] = {"path": "x.cs"}
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("must be a list" in e for e in errs)

    def test_seam_records_may_carry_it_too(self, tmp_path):
        rec = {
            "unit": "seam/damage_pipeline",
            "game_sources": [{"path": "FixtureRelic.cs", "sha256": "0" * 64}],
            "sim_sources": [{"path": "sts2_rl/cmds.py", "sha256": "0" * 64}],
            "extra_sources": [{"path": "nope", "sha256": "z", "side": "game"}],
            "steps": [{"what": "ordering", "verdict": "faithful"}],
            "guards": [],
            "verdict": "faithful",
            "audited": "2026-07-24",
        }
        errs = harness.validate_record(rec, game_root=tmp_path)
        assert any("extra_sources[0]" in e for e in errs)

    def test_source_base_routes_by_side(self, tmp_path):
        assert harness.source_base("game", tmp_path) == tmp_path
        assert harness.source_base("sim", tmp_path) == harness._REPO


class TestRehash:
    def _record_with_drift(self, tmp_path):
        cs = tmp_path / "FixtureRelic.cs"
        cs.write_text(FIXTURE_CS, encoding="utf-8")
        extra = tmp_path / "Extra.cs"
        extra.write_text("public class Extra {}\n", encoding="utf-8")
        rec = _valid_record(harness, tmp_path)
        rec["game_source"]["sha256"] = "0" * 64            # drifted
        rec["sim_source"]["path"] = "sts2_rl/cmds.py"      # drifted ("0"*64)
        rec["extra_sources"] = [
            {"path": "Extra.cs", "sha256": "1" * 64, "side": "game"},
            {"path": "sts2_rl/hooks.py", "sha256": "2" * 64, "side": "sim"},
        ]
        return rec

    def test_repins_every_shape(self, tmp_path):
        rec = self._record_with_drift(tmp_path)
        changes = harness.rehash_record(rec, game_root=tmp_path)
        assert len(changes) == 4, changes
        assert rec["game_source"]["sha256"] == harness.file_sha256(
            tmp_path / "FixtureRelic.cs")
        assert rec["extra_sources"][0]["sha256"] == harness.file_sha256(
            tmp_path / "Extra.cs")
        assert rec["extra_sources"][1]["sha256"] == harness.file_sha256(
            harness._REPO / "sts2_rl/hooks.py")

    def test_idempotent(self, tmp_path):
        rec = self._record_with_drift(tmp_path)
        harness.rehash_record(rec, game_root=tmp_path)
        assert harness.rehash_record(rec, game_root=tmp_path) == []

    def test_missing_file_reported_not_silently_zeroed(self, tmp_path):
        rec = self._record_with_drift(tmp_path)
        rec["extra_sources"][0]["path"] = "Gone.cs"
        changes = harness.rehash_record(rec, game_root=tmp_path)
        assert any("MISSING" in c for c in changes)
        assert rec["extra_sources"][0]["sha256"] == "1" * 64

    def test_seam_plural_lists_repinned(self, tmp_path):
        cs = tmp_path / "Seam.cs"
        cs.write_text("public class Seam {}\n", encoding="utf-8")
        rec = {
            "unit": "seam/fixture",
            "game_sources": [{"path": "Seam.cs", "sha256": "0" * 64}],
            "sim_sources": [{"path": "sts2_rl/cmds.py", "sha256": "0" * 64}],
        }
        harness.rehash_record(rec, game_root=tmp_path)
        assert rec["game_sources"][0]["sha256"] == harness.file_sha256(cs)
        assert rec["sim_sources"][0]["sha256"] == harness.file_sha256(
            harness._REPO / "sts2_rl/cmds.py")

    def test_bulk_writes_the_file(self, tmp_path):
        adir = tmp_path / "records"
        (adir / "relic").mkdir(parents=True)
        rec = self._record_with_drift(tmp_path)
        p = adir / "relic" / "fixture_relic.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        harness.rehash(["relic/fixture_relic"], game_root=tmp_path,
                       audits_dir=adir)
        after = json.loads(p.read_text(encoding="utf-8"))
        assert after["game_source"]["sha256"] == harness.file_sha256(
            tmp_path / "FixtureRelic.cs")

    def test_dry_run_leaves_the_file_alone(self, tmp_path):
        adir = tmp_path / "records"
        (adir / "relic").mkdir(parents=True)
        rec = self._record_with_drift(tmp_path)
        p = adir / "relic" / "fixture_relic.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
        harness.rehash(["relic/fixture_relic"], game_root=tmp_path,
                       audits_dir=adir, write=False)
        assert json.loads(p.read_text(encoding="utf-8")) == rec

    def test_cli_prints_the_not_a_re_audit_warning(self, tmp_path, capsys):
        adir = tmp_path / "records"
        (adir / "relic").mkdir(parents=True)
        (adir / "relic" / "fixture_relic.json").write_text(
            json.dumps(self._record_with_drift(tmp_path)), encoding="utf-8")
        harness.main(["rehash", str(adir / "relic" / "fixture_relic.json"),
                      "--dry-run"])
        err = capsys.readouterr().err
        assert "REHASH IS NOT A RE-AUDIT" in err
        assert "re-audited" in err


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
