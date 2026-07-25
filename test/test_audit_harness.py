"""Tests for the audit completeness harness (tools/audit/harness.py)."""
from __future__ import annotations

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
