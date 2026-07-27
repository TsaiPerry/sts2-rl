# Source-to-Sim Audit Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent-driven audit pipeline from
`docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md`: a
mechanical completeness harness + audit ledger + status tool, order-pinning
hook tests, six engine-seam audits, and batched content audits — proving the
sim encodes the same rules as the decompiled game source without run
recordings.

**Architecture:** Agents read both codebases and write per-unit JSON verdict
records into `audit/records/`; a deliberately dumb harness (`audit/tools/harness.py`)
enumerates units and C# hook overrides, hashes sources, and rejects incomplete
records; `audit/tools/audit_status.py` reports coverage/staleness/gaps. Ordering
semantics are pinned by hook-trace tests in `test/test_hook_order.py`.

**Tech Stack:** Python stdlib only (no new dependencies). Pytest for tests.
The decompiled C# game source is read-only ground truth.

## Global Constraints

- **Commits: authorized for THIS branch only.** This plan executes in an
  isolated worktree `c:\Users\Perry\Desktop\sts2-rl-audit` on branch
  `audit-pipeline`. Perry explicitly authorized per-task commits on that
  branch (2026-07-24) so the review loop has diffs to work from. Therefore:
  commit each task on `audit-pipeline`; **NEVER `git push`**, never commit on
  or merge into `main` — Perry reviews and merges the branch himself.
  (This is a scoped exception to CLAUDE.md rule 4; every "Stage" step below
  becomes `git add` + `git commit` on this branch.)
- Game source root: `c:\Users\Perry\Desktop\Slay the Spire 2`, overridable
  via env var `STS2_GAME_SRC`. Never modify anything under it.
- Sim repo root (all relative paths below): the worktree root
  `c:\Users\Perry\Desktop\sts2-rl-audit` (same repo as
  `c:\Users\Perry\Desktop\sts2-rl`, different checkout).
- Run tests with `py -m pytest test/ -q` (the `py` launcher; repo root cwd).
- **Potions are out of scope** (explicitly deferred by Perry). Ascension
  values out of scope (sim uses non-ascension numbers).
- Audit verdict vocabulary, in rollup precedence order (low→high):
  `faithful`, `waiver`, `deliberate-divergence`, `gap`.
- Audit tasks record gaps; they do NOT fix engine code. Gap fixes are
  follow-up work queued from the ledger (each will land with its own
  failing-then-passing test, but outside this plan).
- The full suite currently passes (2265 passed / 5 xfailed as of
  2026-07-23); no task may regress it.

---

### Task 1: Harness core — roster, override enumeration, hashing

**Files:**
- Create: `audit/tools/harness.py`
- Create: `audit/tools/name_overrides.json`
- Test: `test/test_audit_harness.py`

**Interfaces:**
- Produces (used by Tasks 2, 3, 11–16):
  - `harness.GAME_MODEL_DIRS: dict[str, str]` — kind → C# dir (kinds:
    `relic`, `power`, `card`, `monster`, `event`, `enchantment`)
  - `harness.VERDICTS: tuple[str, ...]` — precedence low→high
  - `harness.list_overrides(cs_text: str) -> list[str]`
  - `harness.file_sha256(path: Path) -> str`
  - `harness.roster(kind: str, game_root: Path | None = None) -> list[dict]`
    — rows `{"unit", "sim_path", "game_path", "game_exists"}` (paths as str)
  - `harness.unported(kind: str, game_root: Path | None = None) -> list[str]`
  - `harness._pascal(unit_id: str) -> str`, `harness._snake(name: str) -> str`
  - CLI: `py audit/tools/harness.py roster [KIND]`

- [ ] **Step 1: Write the failing tests**

Create `test/test_audit_harness.py`:

```python
"""Tests for the audit completeness harness (audit/tools/harness.py)."""
from __future__ import annotations

from pathlib import Path

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest test/test_audit_harness.py -q`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'audit.tools'` (namespace-package import of a file that doesn't exist yet).

- [ ] **Step 3: Create `audit/tools/name_overrides.json`**

```json
{}
```

(Keys will be `"kind/unit_id"` → repo-relative C# path under the game root,
filled in as roster runs surface name mismatches.)

- [ ] **Step 4: Write `audit/tools/harness.py`**

```python
"""Completeness harness for the source-to-sim audit pipeline.

Design: docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md.
Deliberately dumb — enumeration, hashing, and record validation only; it
never judges faithfulness. Agents write the audit records; this tool makes
sure they cannot skip a unit, skip a hook, or leave a verdict vague.

Usage:
  py audit/tools/harness.py roster [KIND]       # work queue + unmatched units
  py audit/tools/harness.py skeleton UNIT       # (Task 2) write record skeleton
  py audit/tools/harness.py validate [PATH...]  # (Task 2) validate records
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
import pkgutil
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

DEFAULT_GAME_ROOT = Path(
    os.environ.get("STS2_GAME_SRC", r"c:\Users\Perry\Desktop\Slay the Spire 2")
)
DEFAULT_AUDITS_DIR = _REPO / "audits"
NAME_OVERRIDES_PATH = Path(__file__).with_name("name_overrides.json")

# Audit verdicts in rollup precedence order (low -> high).
VERDICTS = ("faithful", "waiver", "deliberate-divergence", "gap")

GAME_MODEL_DIRS = {
    "relic": "src/Core/Models/Relics",
    "power": "src/Core/Models/Powers",
    "card": "src/Core/Models/Cards",
    "monster": "src/Core/Models/Monsters",
    "event": "src/Core/Models/Events",
    "enchantment": "src/Core/Models/Enchantments",
}

# `public override <type> <Name>(  |  => ...  |  { ...` — one-regex scan of
# the decompiled output, which is uniform. Captures the member name whether
# it is a method or an expression-bodied property.
_OVERRIDE_RE = re.compile(
    r"^\s*public\s+override\s+(?:sealed\s+)?(?:async\s+)?"
    r"[\w<>,.?\[\] ]+?\s(\w+)\s*(?:\(|=>|\{|$)",
    re.M,
)


def list_overrides(cs_text: str) -> list[str]:
    """Names of every `public override` member, in declaration order."""
    seen: set[str] = set()
    out: list[str] = []
    for name in _OVERRIDE_RE.findall(cs_text):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def file_sha256(path: Path) -> str:
    """sha256 of the file's text with line endings normalized to LF."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _pascal(unit_id: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in unit_id.split("_"))


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _load_name_overrides() -> dict[str, str]:
    return json.loads(NAME_OVERRIDES_PATH.read_text(encoding="utf-8"))


def _sim_units(kind: str) -> dict[str, type]:
    """unit_id -> sim class, from the sim's own registries."""
    if kind == "relic":
        from sts2_rl.relics import ALL_RELICS
        return dict(ALL_RELICS)
    if kind == "power":
        from sts2_rl.powers import ALL_POWERS
        return dict(ALL_POWERS)
    if kind == "card":
        import sts2_rl.cards  # noqa: F401 — triggers registration imports
        from sts2_rl.cards.base import _CARD_CLASSES
        return dict(_CARD_CLASSES)
    if kind == "event":
        from sts2_rl.events import ALL_EVENTS
        return dict(ALL_EVENTS)
    if kind == "enchantment":
        from sts2_rl.enchantments import ALL_ENCHANTMENTS
        return dict(ALL_ENCHANTMENTS)
    if kind == "monster":
        return _monster_units()
    raise ValueError(f"unknown kind: {kind}")


def _monster_units() -> dict[str, type]:
    """Walk the four act packages and collect Monster subclasses by module."""
    from sts2_rl.monsters.base import Monster

    units: dict[str, type] = {}
    for act in ("overgrowth", "underdocks", "hive", "glory"):
        pkg = importlib.import_module(f"sts2_rl.monsters.{act}")
        for info in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"sts2_rl.monsters.{act}.{info.name}")
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(cls, Monster)
                    and cls is not Monster
                    and cls.__module__ == mod.__name__
                ):
                    units[_snake(cls.__name__)] = cls
    return units


def _game_path(kind: str, unit_id: str, game_root: Path,
               overrides: dict[str, str]) -> Path:
    key = f"{kind}/{unit_id}"
    if key in overrides:
        return game_root / overrides[key]
    suffix = "Power" if kind == "power" else ""
    return game_root / GAME_MODEL_DIRS[kind] / f"{_pascal(unit_id)}{suffix}.cs"


def roster(kind: str, game_root: Path | None = None) -> list[dict]:
    """The audit work queue for one kind (see module docstring)."""
    root = game_root or DEFAULT_GAME_ROOT
    overrides = _load_name_overrides()
    rows = []
    for unit_id, cls in sorted(_sim_units(kind).items()):
        gp = _game_path(kind, unit_id, root, overrides)
        sim_file = inspect.getsourcefile(cls)
        rows.append({
            "unit": f"{kind}/{unit_id}",
            "sim_path": str(Path(sim_file).resolve().relative_to(_REPO)),
            "game_path": str(gp.relative_to(root)),
            "game_exists": gp.is_file(),
        })
    return rows


def unported(kind: str, game_root: Path | None = None) -> list[str]:
    """C# model files in this kind's directory matched by no sim unit.

    Informational: many are out of Ironclad scope, not gaps."""
    root = game_root or DEFAULT_GAME_ROOT
    matched = {
        Path(r["game_path"]).name
        for r in roster(kind, root)
        if r["game_exists"]
    }
    model_dir = root / GAME_MODEL_DIRS[kind]
    return sorted(
        p.name for p in model_dir.glob("*.cs") if p.name not in matched
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = ap_roster = sub.add_parser("roster", help="print the audit work queue")
    ap_roster.add_argument("kind", nargs="?", choices=sorted(GAME_MODEL_DIRS))
    del r
    args = ap.parse_args(argv)

    if args.cmd == "roster":
        kinds = [args.kind] if args.kind else sorted(GAME_MODEL_DIRS)
        for kind in kinds:
            rows = roster(kind)
            unmatched = [x for x in rows if not x["game_exists"]]
            extra = unported(kind)
            print(f"{kind}: {len(rows)} sim units, "
                  f"{len(unmatched)} unmatched, {len(extra)} unported C# files")
            for x in unmatched:
                print(f"  UNMATCHED {x['unit']} -> expected {x['game_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest test/test_audit_harness.py -q`
Expected: all PASS. If `test_relic_roster_includes_unsettling_lamp` or
`test_monster_roster_nonempty_and_snake_ids` fails, the failure is real
information (registry import name or path convention differs) — fix the
harness against the actual registry, never the assertion's intent.

- [ ] **Step 6: Run the roster once for real; record name mismatches**

Run: `py audit/tools/harness.py roster`
Expected: per-kind lines. For each `UNMATCHED` line, find the real C# file
(`Grep` for `class <PascalName>` under the game root's `src/Core/Models/`)
and add an entry to `audit/tools/name_overrides.json`, e.g.:

```json
{
  "relic/some_relic": "src/Core/Models/Relics/SomeRelicRealName.cs"
}
```

Re-run until `unmatched` is 0 for every kind, or the residue is genuinely
sim-only content (document any such residue in the task's completion report).

- [ ] **Step 7: Run the full suite**

Run: `py -m pytest test/ -q`
Expected: no regressions (baseline: 2265 passed / 5 xfailed, plus the new
harness tests).

- [ ] **Step 8: Stage and commit (on `audit-pipeline` only)**

```powershell
git add audit/tools/harness.py audit/tools/name_overrides.json test/test_audit_harness.py
git commit -m "feat(audit): completeness harness roster, override enumeration, hashing"
```

---

### Task 2: Skeleton generation, record validation, and the audit prompt

**Files:**
- Modify: `audit/tools/harness.py` (append functions; extend `main`)
- Create: `audit/tools/PROMPT.md`
- Create: `audit/records/` (directory; created on first skeleton)
- Test: `test/test_audit_harness.py` (append test classes)

**Interfaces:**
- Consumes: Task 1's `roster`, `list_overrides`, `file_sha256`,
  `_game_path`, `_load_name_overrides`, `VERDICTS`, `DEFAULT_AUDITS_DIR`.
- Produces (used by Tasks 3, 5–16):
  - `harness.SEAMS: tuple[str, ...]` and `harness.SEAM_SOURCES: dict[str, tuple[list[str], list[str]]]`
  - `harness.skeleton(unit: str, game_root: Path | None = None, audits_dir: Path | None = None) -> Path`
  - `harness.validate_record(record: dict, game_root: Path | None = None) -> list[str]`
    (empty list = valid)
  - CLI: `py audit/tools/harness.py skeleton relic/unsettling_lamp`,
    `py audit/tools/harness.py validate [PATH...]` (no paths = all of `audit/records/`)
  - Record schema (content kinds): `unit`, `game_source{path,sha256}`,
    `sim_source{path,sha256}`, `hooks{<Name>: {maps_to, verdict, rationale?, issue?}}`,
    `guards[{what, verdict, rationale?, issue?}]`, `verdict`, `audited` (YYYY-MM-DD)
  - Record schema (seams): `unit`, `game_sources[{path,sha256}]`,
    `sim_sources[{path,sha256}]`, `steps[{what, verdict, rationale?, issue?}]`,
    `guards[...]`, `verdict`, `audited`

- [ ] **Step 1: Write the failing tests**

Append to `test/test_audit_harness.py`:

```python
import json


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest test/test_audit_harness.py -q`
Expected: new tests FAIL with `AttributeError` (`validate_record`,
`skeleton` not defined); Task 1 tests still pass.

- [ ] **Step 3: Append the implementation to `audit/tools/harness.py`**

```python
# ── Seams (Tier 2) ────────────────────────────────────────────────────────
# Engine seams audited as ordering specs, not per-hook records. Paths are
# repo-relative (game side under the game root). If a listed C# file does
# not exist, locate the real one with a grep and fix this table.
SEAM_SOURCES: dict[str, tuple[list[str], list[str]]] = {
    "damage_pipeline": (
        ["src/Core/Commands/DamageCmd.cs"],
        ["sts2_rl/cmds.py", "sts2_rl/valueprops.py"],
    ),
    "power_cmd": (
        ["src/Core/Commands/PowerCmd.cs"],
        ["sts2_rl/cmds.py"],
    ),
    "creature_card_cmds": (
        ["src/Core/Commands/CreatureCmd.cs", "src/Core/Commands/PlayerCmd.cs",
         "src/Core/Commands/CardCmd.cs", "src/Core/Commands/CardPileCmd.cs"],
        ["sts2_rl/cmds.py"],
    ),
    "turn_structure": (
        ["src/Core/Combat/CombatManager.cs", "src/Core/Combat/PlayerTurnPhase.cs"],
        ["sts2_rl/combat.py", "sts2_rl/player.py"],
    ),
    "hook_dispatch": (
        ["src/Core/Hooks/Hook.cs", "src/Core/Models/AbstractModel.cs"],
        ["sts2_rl/hooks.py"],
    ),
    "monster_state_machine": (
        ["src/Core/MonsterMoves/MonsterMoveStateMachine.cs"],
        ["sts2_rl/monsters/state_machine.py"],
    ),
}
SEAMS: tuple[str, ...] = tuple(SEAM_SOURCES)


def _hash_sources(paths: list[str], base: Path) -> list[dict]:
    return [{"path": p, "sha256": file_sha256(base / p)} for p in paths]


def skeleton(unit: str, game_root: Path | None = None,
             audits_dir: Path | None = None) -> Path:
    """Write audit/records/<kind>/<id>.json with hooks/steps enumerated and
    verdicts empty, ready for an agent to fill in. Refuses to overwrite."""
    root = game_root or DEFAULT_GAME_ROOT
    adir = audits_dir or DEFAULT_AUDITS_DIR
    kind, _, unit_id = unit.partition("/")

    if kind == "seam":
        game_paths, sim_paths = SEAM_SOURCES[unit_id]
        record: dict = {
            "unit": unit,
            "game_sources": _hash_sources(game_paths, root),
            "sim_sources": _hash_sources(sim_paths, _REPO),
            "steps": [],
            "guards": [],
            "verdict": "",
            "audited": "",
        }
    else:
        row = next(r for r in roster(kind, root) if r["unit"] == unit)
        gp = root / row["game_path"]
        record = {
            "unit": unit,
            "game_source": {"path": row["game_path"], "sha256": file_sha256(gp)},
            "sim_source": {"path": row["sim_path"],
                           "sha256": file_sha256(_REPO / row["sim_path"])},
            "hooks": {
                name: {"maps_to": "", "verdict": ""}
                for name in list_overrides(gp.read_text(encoding="utf-8-sig",
                                                        errors="replace"))
            },
            "guards": [],
            "verdict": "",
            "audited": "",
        }

    out = Path(adir) / kind / f"{unit_id}.json"
    if out.exists():
        raise FileExistsError(f"{out} exists — delete it explicitly to re-audit")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return out


def _check_entry(where: str, entry: dict, errs: list[str]) -> None:
    v = entry.get("verdict", "")
    if v not in VERDICTS:
        errs.append(f"{where}: verdict {v!r} not one of {VERDICTS}")
        return
    if v in ("waiver", "deliberate-divergence") and not entry.get("rationale"):
        errs.append(f"{where}: verdict {v!r} requires a non-empty rationale")
    if v == "gap" and not entry.get("issue"):
        errs.append(f"{where}: verdict 'gap' requires a non-empty issue")


def validate_record(record: dict, game_root: Path | None = None) -> list[str]:
    """Completeness/vocabulary validation. Returns error strings; [] = valid.
    Staleness (hash drift) is audit_status.py's job, not validation's."""
    root = game_root or DEFAULT_GAME_ROOT
    errs: list[str] = []
    unit = record.get("unit", "")
    kind, _, unit_id = unit.partition("/")
    if not kind or not unit_id:
        return [f"bad unit id: {unit!r}"]

    entries: list[dict] = []

    if kind == "seam":
        for side in ("game_sources", "sim_sources"):
            srcs = record.get(side) or []
            if not srcs:
                errs.append(f"{side}: at least one source required")
            for i, s in enumerate(srcs):
                if not s.get("path") or not s.get("sha256"):
                    errs.append(f"{side}[{i}]: path and sha256 required")
        steps = record.get("steps") or []
        if not steps:
            errs.append("seam record requires non-empty steps")
        for i, s in enumerate(steps):
            if not s.get("what"):
                errs.append(f"steps[{i}]: 'what' required")
            _check_entry(f"steps[{i}]", s, errs)
        entries += steps
    else:
        for side in ("game_source", "sim_source"):
            src = record.get(side) or {}
            if not src.get("path") or not src.get("sha256"):
                errs.append(f"{side}: path and sha256 required")
        hooks = record.get("hooks")
        if hooks is None:
            errs.append("hooks section required")
            hooks = {}
        gp = root / (record.get("game_source") or {}).get("path", "")
        if gp.is_file():
            required = set(list_overrides(
                gp.read_text(encoding="utf-8-sig", errors="replace")))
            missing = required - set(hooks)
            if missing:
                errs.append(
                    f"hooks missing verdicts for overrides: {sorted(missing)}")
        else:
            errs.append(f"game source not found: {gp}")
        for name, entry in hooks.items():
            _check_entry(f"hooks[{name}]", entry, errs)
            if entry.get("verdict") == "faithful" and not entry.get("maps_to"):
                errs.append(f"hooks[{name}]: 'faithful' requires maps_to")
        entries += list(hooks.values())

    guards = record.get("guards") or []
    for i, g in enumerate(guards):
        if not g.get("what"):
            errs.append(f"guards[{i}]: 'what' required")
        _check_entry(f"guards[{i}]", g, errs)
    entries += guards

    verdicts = [e.get("verdict") for e in entries if e.get("verdict") in VERDICTS]
    if verdicts:
        worst = max(verdicts, key=VERDICTS.index)
        if record.get("verdict") != worst:
            errs.append(
                f"unit verdict {record.get('verdict')!r} != rollup {worst!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("audited") or ""):
        errs.append("audited must be YYYY-MM-DD")
    return errs
```

Extend `main` — add the two subparsers and their handling:

```python
    ap_skel = sub.add_parser("skeleton", help="write a record skeleton")
    ap_skel.add_argument("unit", help="e.g. relic/unsettling_lamp or seam/power_cmd")
    ap_val = sub.add_parser("validate", help="validate audit records")
    ap_val.add_argument("paths", nargs="*", help="record files (default: all)")
```

```python
    if args.cmd == "skeleton":
        out = skeleton(args.unit)
        print(f"wrote {out}")
    if args.cmd == "validate":
        paths = ([Path(p) for p in args.paths]
                 or sorted(DEFAULT_AUDITS_DIR.rglob("*.json")))
        bad = 0
        for p in paths:
            errs = validate_record(json.loads(p.read_text(encoding="utf-8")))
            for e in errs:
                print(f"{p}: {e}")
            bad += bool(errs)
        print(f"{len(paths)} record(s), {bad} invalid")
        return 1 if bad else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_audit_harness.py -q`
Expected: all PASS.

- [ ] **Step 5: Verify every SEAM_SOURCES path exists**

Run: `py -c "from audit.tools import harness; from pathlib import Path; [print(p, (harness.DEFAULT_GAME_ROOT / p).is_file()) for ps in (v[0] for v in harness.SEAM_SOURCES.values()) for p in ps]"`
Expected: every line ends `True`. For any `False`, locate the real file
(Grep for its class name under the game root `src/`) and correct
`SEAM_SOURCES`. Also spot-check the sim side the same way against `_REPO`.

- [ ] **Step 6: Write `audit/tools/PROMPT.md`**

```markdown
# Audit prompt — source-to-sim unit audits (v1)

You are auditing ONE ported unit for behavioral fidelity: the decompiled C#
model (ground truth) vs the sim implementation. You judge; the harness only
checks completeness. Read BOTH files fully before writing any verdict.

## Procedure

1. `py audit/tools/harness.py skeleton <kind>/<id>` (skip if the record
   exists from a previous incomplete pass — then re-read it critically).
2. Read the C# file top to bottom. List for yourself: every override, every
   guard clause / early return, every numeric constant (take the
   NON-ascension branch of `AscensionHelper.GetValueIfAscension(...)`),
   every state field and when it resets.
3. Read the sim counterpart the same way.
4. Fill the record: for each hook, `maps_to` (the sim method(s) — the sim
   re-architects, so one C# hook may map to a bracket of sim hooks) and a
   verdict. Record guard-level findings in `guards` — one entry per guard
   that needed thought, not only per problem.
5. Verdicts: `faithful` | `waiver` (unreachable in Ironclad-only sim scope —
   rationale required) | `deliberate-divergence` (sim models it differently
   on purpose — rationale required) | `gap` (real divergence — `issue`
   required, describing the observable wrong behavior). NEVER fix engine
   code during an audit; record the gap.
6. `py audit/tools/harness.py validate audit/records/<kind>/<id>.json` must pass.

## Known bug classes — check EVERY one against your unit

1. **Hook order at seams**: effects that must precede/follow Artifact
   interception, block absorption, or death checks (Unsettling Lamp fired
   through an Artifact-negated debuff).
2. **Killing-blow guards**: C# often skips the victim's after-damage hooks
   on death (`CreatureCmd.cs:392`-style `!WasTargetKilled || !IsDead`).
3. **Sign-aware power typing**: `GetTypeForAmount(amount)` — negative
   Dexterity IS a Debuff; `power_type` class attrs alone miss this.
4. **Visibility guards**: `power.IsVisible` gates several relic triggers.
5. **Temporary-power double-dip**: `ITemporaryPower.InternallyAppliedPower`
   (doubling a wrapper must not also double its internal power).
6. **State-machine int args**: `AddBranch` integers are weight OR cooldown
   OR maxRepeats depending on position/overload — misreading produced the
   TwigSlimeM/Flyconid bug. Verify against the RandomBranchState overloads.
7. **Pile limbo**: a card mid-OnPlay is in `PileType.Play`, so a reshuffle
   it triggers excludes it.
8. **Append position**: out-of-combat transform APPENDS at deck end
   (`CardCmd.cs:437`); random picks are StableShuffle + take-first;
   StableShuffle ties keep incoming order, sorted on UPPERCASE id.
9. **Per-Replay iteration**: the game builds a fresh CardPlay per Replay
   loop iteration; the sim fires `before_card_played` once per play.
10. **Reset timing**: when does per-combat/per-turn state clear —
    BeforeCombatStart vs AfterCombatEnd vs turn boundaries; compare exactly.

## Scope

Potions: out of scope entirely. Ascension values: out of scope. Characters
other than Ironclad: `waiver` with rationale. Multiplayer-only params
(PlayerChoiceContext etc.): note in `maps_to` mapping, not a divergence by
themselves.
```

- [ ] **Step 7: Smoke the CLI end-to-end on the real Lamp**

```powershell
py audit/tools/harness.py skeleton relic/unsettling_lamp
py audit/tools/harness.py validate audit/records/relic/unsettling_lamp.json
```

Expected: skeleton written listing `Rarity`, `BeforeCombatStart`,
`BeforePowerAmountChanged`, `ModifyPowerAmountGivenMultiplicative`,
`AfterCardPlayed`, `AfterCombatEnd`; validate reports errors (empty
verdicts) and exits 1 — that's the harness doing its job. Delete the
skeleton afterwards (`Remove-Item audit/records/relic/unsettling_lamp.json`) —
Task 11 audits it for real.

- [ ] **Step 8: Run the full suite, then stage**

Run: `py -m pytest test/ -q` — no regressions.

```powershell
git add audit/tools/harness.py audit/tools/PROMPT.md test/test_audit_harness.py
git commit -m "feat(audit): record skeletons, validation, and the audit prompt"
```

---

### Task 3: `audit/tools/audit_status.py` — coverage, staleness, gaps

**Files:**
- Create: `audit/tools/audit_status.py`
- Test: `test/test_audit_status.py`

**Interfaces:**
- Consumes: `harness.roster`, `harness.SEAMS`, `harness.validate_record`,
  `harness.file_sha256`, `harness.GAME_MODEL_DIRS`, `harness.DEFAULT_AUDITS_DIR`.
- Produces:
  - `audit_status.collect(kinds=None, game_root=None, audits_dir=None) -> dict`
    — `{kind: {"total", "audited", "invalid", "stale", "gaps", "unaudited": [...]}}`
  - CLI: `py audit/tools/audit_status.py [--strict] [--kind KIND]`
    Exit codes: 2 = invalid records; 1 = (`--strict` only) stale or open
    gaps or unaudited > 0; 0 otherwise.

- [ ] **Step 1: Write the failing tests**

Create `test/test_audit_status.py`:

```python
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
```

(`audit_status.main` must therefore resolve its defaults from
`harness.DEFAULT_GAME_ROOT` / `harness.DEFAULT_AUDITS_DIR` at call time —
pass them through to `collect(...)` inside `main` rather than baking them
into argument defaults, so the monkeypatching above works.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest test/test_audit_status.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'audit.tools.audit_status'`.

- [ ] **Step 3: Write `audit/tools/audit_status.py`**

```python
"""Audit ledger status: coverage, staleness, open gaps.

Aggregates audit/records/ against the harness roster and both source trees.

  py audit/tools/audit_status.py                # report, exit 0 (2 if invalid records)
  py audit/tools/audit_status.py --strict       # also exit 1 on stale/gaps/unaudited
  py audit/tools/audit_status.py --kind relic   # one kind (or "seam")

Success statement this enables: "N of M in-scope units audited faithful,
zero stale, zero open gaps."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools import harness


def _is_stale(record: dict, game_root: Path) -> bool:
    def drifted(src: dict, base: Path) -> bool:
        p = base / src.get("path", "")
        return (not p.is_file()) or harness.file_sha256(p) != src.get("sha256")

    if record["unit"].startswith("seam/"):
        return (any(drifted(s, game_root) for s in record.get("game_sources", []))
                or any(drifted(s, _REPO) for s in record.get("sim_sources", [])))
    return (drifted(record.get("game_source", {}), game_root)
            or drifted(record.get("sim_source", {}), _REPO))


def collect(kinds=None, game_root: Path | None = None,
            audits_dir: Path | None = None) -> dict:
    root = game_root or harness.DEFAULT_GAME_ROOT
    adir = Path(audits_dir or harness.DEFAULT_AUDITS_DIR)
    kinds = tuple(kinds) if kinds else tuple(sorted(harness.GAME_MODEL_DIRS)) + ("seam",)

    out: dict = {}
    for kind in kinds:
        if kind == "seam":
            units = [f"seam/{s}" for s in harness.SEAMS]
        else:
            units = [r["unit"] for r in harness.roster(kind, root)]
        stats = {"total": len(units), "audited": 0, "invalid": 0,
                 "stale": 0, "gaps": 0, "unaudited": []}
        for unit in units:
            path = adir / kind / (unit.split("/", 1)[1] + ".json")
            if not path.is_file():
                stats["unaudited"].append(unit)
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            errs = harness.validate_record(record, game_root=root)
            if errs:
                stats["invalid"] += 1
                continue
            stats["audited"] += 1
            if _is_stale(record, root):
                stats["stale"] += 1
            if record.get("verdict") == "gap":
                stats["gaps"] += 1
        out[kind] = stats
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on stale, gaps, or unaudited units")
    ap.add_argument("--kind", choices=tuple(sorted(harness.GAME_MODEL_DIRS)) + ("seam",))
    args = ap.parse_args(argv)

    stats = collect(kinds=(args.kind,) if args.kind else None)
    invalid = stale = gaps = unaudited = 0
    print(f"{'kind':<12}{'total':>6}{'audited':>9}{'invalid':>9}"
          f"{'stale':>7}{'gaps':>6}{'unaudited':>11}")
    for kind, s in stats.items():
        print(f"{kind:<12}{s['total']:>6}{s['audited']:>9}{s['invalid']:>9}"
              f"{s['stale']:>7}{s['gaps']:>6}{len(s['unaudited']):>11}")
        invalid += s["invalid"]
        stale += s["stale"]
        gaps += s["gaps"]
        unaudited += len(s["unaudited"])
    if invalid:
        return 2
    if args.strict and (stale or gaps or unaudited):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_audit_status.py test/test_audit_harness.py -q`
Expected: all PASS.

- [ ] **Step 5: Run against the real (empty) ledger**

Run: `py audit/tools/audit_status.py`
Expected: a table with every kind fully unaudited, seams total 6, exit 0.
This is the baseline the audit batches burn down.

- [ ] **Step 6: Run the full suite, then stage**

Run: `py -m pytest test/ -q` — no regressions.

```powershell
git add audit/tools/audit_status.py test/test_audit_status.py
git commit -m "feat(audit): audit_status coverage/staleness/gap reporting"
```

---

### Task 4: Hook-order tracing infrastructure + damage-pipeline pin

**Files:**
- Create: `test/test_hook_order.py`

**Interfaces:**
- Produces (used by Tasks 5–10): `trace(hooks, names) -> list[str]` — wraps
  the named `HookSystem` instance methods so each invocation appends its
  hook name to the returned list, then delegates to the original.

- [ ] **Step 1: Write the file with the helper and the first pinned tests**

```python
"""Order-tracing tests pinning engine-seam hook sequences (Tier 2 of
docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md).

`trace` wraps HookSystem instance methods to record invocation order. These
tests are the durable form of the seam audits: a future edit cannot
silently reorder a pipeline without a failure here.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, DamageCmd
from sts2_rl.cards import StrikeCard


def trace(hooks, names):
    """Record invocation order of the named hooks on this HookSystem."""
    calls: list[str] = []
    for name in names:
        orig = getattr(hooks, name)

        def make(name=name, orig=orig):
            def wrapper(*args, **kwargs):
                calls.append(name)
                return orig(*args, **kwargs)
            return wrapper

        setattr(hooks, name, make())
    return calls


PIPELINE = [
    "modify_damage_additive",
    "modify_damage_multiplicative",
    "modify_damage_cap",
    "on_attacked",
    "modify_hp_lost",
    "should_die",
    "on_damage_received",
]


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


class TestDamagePipelineOrder:
    def test_non_lethal_hit_order(self):
        """DamageCmd.deal source order: additive -> multiplicative -> cap ->
        on_attacked -> block -> modify_hp_lost -> apply -> (death check) ->
        on_damage_received. should_die must NOT fire on a non-lethal hit."""
        cs = fresh()
        calls = trace(cs.hooks, PIPELINE)
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player, card=StrikeCard())
        assert [c for c in calls if c in PIPELINE] == [
            "modify_damage_additive",
            "modify_damage_multiplicative",
            "modify_damage_cap",
            "on_attacked",
            "modify_hp_lost",
            "on_damage_received",
        ]

    def test_killing_blow_skips_on_damage_received(self):
        """The game skips the victim's AfterDamageReceived on a kill
        (CreatureCmd.cs:392 `!WasTargetKilled || !IsDead`); the sim guards
        with `if not target.is_dead` in DamageCmd.deal."""
        cs = fresh()
        cs.enemy.hp = 1
        calls = trace(cs.hooks, PIPELINE)
        DamageCmd.deal(cs.hooks, cs.enemy, 6, dealer=cs.player, card=StrikeCard())
        assert "should_die" in calls
        assert "on_damage_received" not in calls
```

- [ ] **Step 2: Run the tests**

Run: `py -m pytest test/test_hook_order.py -v`
Expected: PASS. If the non-lethal order differs, read `DamageCmd.deal` in
`sts2_rl/cmds.py` (the dispatch sequence is at lines ~57–113) and compare
against `DamageCmd.cs` in the game source **before** touching the
expectation: the test exists to pin the C# order, so a mismatch is either a
wrong expectation (fix the test to match the verified C# order) or a real
seam gap (record it — see Global Constraints — and mark the test xfail with
the gap reference). If `cs.enemy` is not the single-enemy accessor, use the
same enemy accessor `test/test_powers.py` uses.

- [ ] **Step 3: Run the full suite, then stage**

Run: `py -m pytest test/ -q` — no regressions.

```powershell
git add test/test_hook_order.py
git commit -m "test(audit): hook-order tracing helper + damage pipeline pins"
```

---

### Tasks 5–10: The six engine-seam audits (Tier 2)

Tasks 5–10 share one procedure, applied to one seam each. **The procedure
below is complete for every one of these tasks** — only the seam name, the
source files (from `harness.SEAM_SOURCES`), the seed facts, and the pinned
tests differ, and those are tabulated per task.

**Shared procedure (every step applies to each of Tasks 5–10):**

- [ ] **Step A: Skeleton.** `py audit/tools/harness.py skeleton seam/<seam>`
  (fix `SEAM_SOURCES` paths first if the skeleton errors on a missing file —
  locate the real C# file by grepping for its class name under the game
  root, correct the table in `audit/tools/harness.py`, and stage that edit).
- [ ] **Step B: Extract the ordering spec.** Read every listed C# file fully.
  Write `audit/seams/<seam>.md`: a numbered list of steps, guards, and
  early returns in execution order, each annotated with the C# file:line it
  came from. Start from the seed facts in the task's table below — they are
  known-correct anchors from past convergence work — then complete the list
  from the source. This document is the durable statement of what the sim
  claims to implement.
- [ ] **Step C: Compare the sim.** Read the sim files listed for the seam.
  For every numbered step in the spec doc, add an entry to the record's
  `steps` array: `{"what": "<n>. <one-line step>", "verdict": ...}` with
  rationale/issue per the vocabulary rules. Follow `audit/tools/PROMPT.md`'s
  bug-class checklist. Gaps are recorded, never fixed inline.
- [ ] **Step D: Pin with order-tracing tests.** For each behavior in the
  task's "pin" table: first check whether an equivalent regression test
  already exists (`Grep` the `test/` directory for the listed search terms);
  if yes, record its path in the spec doc instead of duplicating it; if no,
  add a test to `test/test_hook_order.py` using the `trace` helper and the
  `fresh()` pattern from Task 4 (construct state with `CombatState(rng=
  random.Random(seed))`, apply powers via `PowerCmd.apply(cs.hooks, ...)`,
  deal damage via `DamageCmd.deal(cs.hooks, ...)`, mirroring
  `test/test_powers.py` idioms).
- [ ] **Step E: Fill `audited` (today's date) and unit `verdict` (rollup),
  then validate.** `py audit/tools/harness.py validate audit/records/seam/<seam>.json`
  → exit 0.
- [ ] **Step F: Full suite.** `py -m pytest test/ -q` — no regressions
  (xfails added for recorded gaps are allowed and expected).
- [ ] **Step G: Commit.**
  `git add audit/records/seam/<seam>.json audit/seams/<seam>.md test/test_hook_order.py audit/tools/harness.py`
  then `git commit -m "audit(seam): <seam> ordering audit + pins"` (on
  `audit-pipeline` only).

### Task 5: Seam audit — `damage_pipeline`

**Files:** Create `audit/seams/damage_pipeline.md`,
`audit/records/seam/damage_pipeline.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["damage_pipeline"]`.

Seed facts for Step B (verify each against source; they anchor, not replace, the extraction):

| Seed fact | Origin |
|---|---|
| Pipeline: powered modifiers → cap → on_attacked → block absorption → modify_hp_lost → apply → death check → post-damage events | CLAUDE.md damage-typing section |
| Only MOVE-and-not-UNPOWERED damage goes through Strength/Vulnerable/Weak; only MOVE fires on_attacked | valueprops.py contract |
| Victim's after-damage hooks skipped on a killing blow | CreatureCmd.cs:392; sim `if not target.is_dead` in DamageCmd.deal |
| Thorns deals Unpowered (blockable, unmodified); Poison is UNBLOCKABLE but goes through modify_hp_lost | CLAUDE.md known-intentional behaviors |

Pins for Step D (search terms → add if absent):

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| Killing-blow hook skip | `is_dead` + `on_damage_received`, `test_hive` | already added in Task 4 — record path |
| Unpowered damage skips modifiers | `unpowered` in test_powers.py | trace test: apply StrengthPower, deal UNPOWERED-props damage, assert modify_damage_additive result unused (HP delta = base) |
| Unblockable skips block | `UNBLOCKABLE` | trace/behavior test: enemy with block takes full HP loss |

### Task 6: Seam audit — `power_cmd`

**Files:** Create `audit/seams/power_cmd.md`,
`audit/records/seam/power_cmd.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["power_cmd"]`.

Seed facts:

| Seed fact | Origin |
|---|---|
| `modify_power_amount` runs BEFORE the Artifact early-return in PowerCmd.apply | 2026-07-24 Unsettling Lamp fix (staged) — verify the C# ordering in PowerCmd.cs and cite exact lines |
| Debuffs intercepted by Artifact; buffs never | powers.py convention |
| Power typing is sign-aware in C# (`GetTypeForAmount(amount)`) — negative Dexterity is a Debuff | UnsettlingLamp.cs:97,124 |
| Power visibility (`power.IsVisible`) gates some listeners | UnsettlingLamp.cs:93 |

Pins:

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| modify_power_amount before Artifact veto | `unsettling_lamp` + `artifact` | trace test: enemy with ArtifactPower 1; `PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, ...)`; assert `modify_power_amount` in calls AND enemy has no Vulnerable AND artifact consumed (mirror TestArtifact assertions in test_powers.py; check PowerCmd.apply's signature in cmds.py for the applier parameter before writing) |
| Artifact consumes exactly one stack per debuff | `artifact` in test_powers.py | expected to exist — record path |

### Task 7: Seam audit — `creature_card_cmds`

**Files:** Create `audit/seams/creature_card_cmds.md`,
`audit/records/seam/creature_card_cmds.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["creature_card_cmds"]`.

Seed facts:

| Seed fact | Origin |
|---|---|
| Card mid-OnPlay sits in PileType.Play; a reshuffle it triggers excludes it | SP3 batch 17 (exoskeleton reshuffle) |
| Out-of-combat transform APPENDS at deck end | CardCmd.cs:437 |
| A random card pick = StableShuffle the pile + take First; ties keep incoming order sorted on UPPERCASE id | memory: random-card-pick / stable-shuffle notes |
| Death ≠ removal: a 0-HP creature can persist (withered Decimillipede segments keep taking turns); only removal from Enemies is vetoed | memory: death-does-not-mean-removal |
| Stun skips the move but not turn-start/end effects; escape counts as gone without dying | CLAUDE.md monster AI section |

Pins:

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| Play-limbo reshuffle exclusion | `reshuffle` / `exoskeleton` | behavior test: force a reshuffle mid-card-resolution; assert the resolving card is not in the new draw pile |
| Transform appends at end | `transform` | run-level test asserting deck position after transform |

### Task 8: Seam audit — `turn_structure`

**Files:** Create `audit/seams/turn_structure.md`,
`audit/records/seam/turn_structure.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["turn_structure"]`.

Seed facts:

| Seed fact | Origin |
|---|---|
| end_turn order: player turn-end hooks → in-hand turn-end effects (ethereal, Burn) → discard hand → per-enemy turns (block clear → on_enemy_turn_start → move/stun-skip → on_enemy_turn_end) → on_enemy_side_end (V/W/F tick) → player turn (block clear → energy → on_player_turn_start → draw) | CLAUDE.md turn/combat flow |
| CheckWinCondition runs after the player's turn SETUP; player AfterTurnEnd fires after the hand flush (Parrying Shield) | memory: combat-end/turn-end hook points |
| Combat ends when player dead or every non-minion enemy dead/escaped | combat.py win check |

Pins:

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| Full end_turn hook sequence | `end_turn` + `order` | trace test over one end_turn: assert relative order of on_card_played-free sequence: player turn-end → discard → enemy turn hooks → on_enemy_side_end → on_player_turn_start |
| AfterTurnEnd after hand flush | `parrying_shield` | expected from Parrying Shield port — record path |

### Task 9: Seam audit — `hook_dispatch`

**Files:** Create `audit/seams/hook_dispatch.md`,
`audit/records/seam/hook_dispatch.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["hook_dispatch"]`.

Seed facts:

| Seed fact | Origin |
|---|---|
| Sim dispatch is registration-order over one flat listener list; determine the game's cross-listener ordering (relics vs powers vs cards; owner vs others) from Hook.cs/AbstractModel.cs and give it a verdict | hooks.py `_listeners` |
| No Early/Late hook phases in the sim | CLAUDE.md known gaps — expected `deliberate-divergence` or per-listener waivers |
| `before_card_played` fires once per play, not per Replay iteration | CLAUDE.md known gaps — record as the divergence it is |
| Modifier families: additive=sum, multiplicative=product, chain=fold; predicate short-circuits on any False | hooks.py docstring — verify each against Hook.cs aggregation |

Pins:

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| Listener-order determinism | `register` order in test_new_features.py | trace/behavior test: two listeners registered in order both implementing one additive hook; assert call order = registration order |

### Task 10: Seam audit — `monster_state_machine`

**Files:** Create `audit/seams/monster_state_machine.md`,
`audit/records/seam/monster_state_machine.json`; Modify `test/test_hook_order.py`.
**Sources:** `harness.SEAM_SOURCES["monster_state_machine"]` (add the
RandomBranchState / ConditionalBranchState C# files to the table when
located in Step A — they live beside MonsterMoveStateMachine.cs under
`src/Core/MonsterMoves/`).

Seed facts:

| Seed fact | Origin |
|---|---|
| AddBranch int args are cooldown/maxRepeats in some overloads, weights in others — enumerate every overload signature and document the arg roles | monster-move weight-vs-cooldown bug (TwigSlimeM/Flyconid) |
| Repeat rules: CANNOT_REPEAT / CAN_REPEAT_X_TIMES / USE_ONLY_ONCE + cooldowns keyed off state_log | state_machine.py port |
| The game rolls moves at intent-display time from a dedicated MonsterAi RNG stream; sim uses the shared combat stream | CLAUDE.md known gaps — record verdict |

Pins:

| Behavior | Grep test/ for | If absent, pin |
|---|---|---|
| Weight-vs-cooldown arg handling | `cooldown` in state-machine tests | expected from the TwigSlimeM fix — record path |
| Repeat-rule enforcement | `CAN_REPEAT` / `USE_ONLY_ONCE` | behavior test on a MachineMonster (Byrdonis/Fogmog/Mawler) asserting a move can't repeat past its rule |

---

### Task 11: Tier 1 pilot — first relic batch (15 units) + prompt hardening

**Files:**
- Create: `audit/records/relic/<id>.json` × 15
- Modify: `audit/tools/PROMPT.md` (lessons learned)
- Modify: `audit/tools/name_overrides.json` (as needed)

**Interfaces:**
- Consumes: Task 2's `skeleton`/`validate` CLI and `PROMPT.md`; Task 3's
  status tool.
- Produces: the proven per-unit audit procedure Tasks 12–16 repeat, and a
  hardened PROMPT.md.

- [ ] **Step 1: Pick the batch.** `py audit/tools/harness.py roster relic` —
  take the first 15 units alphabetically. `relic/unsettling_lamp` is
  audited in whichever batch alphabetically contains it; if it is not in
  this first 15, swap it in anyway — it is the worked example from the
  design and calibrates the guard-level depth expected.
- [ ] **Step 2: Audit each unit** following `audit/tools/PROMPT.md` exactly:
  skeleton → read C# fully → read sim fully → fill hooks/guards/verdicts →
  validate. For Unsettling Lamp specifically, the record must contain guard
  entries for `power.IsVisible`, sign-aware `GetTypeForAmount`, and the
  `ITemporaryPower` double-dip, each with a real verdict (the design's §
  worked example — waiver rationales must name what makes them unreachable,
  not just say "out of scope").
- [ ] **Step 3: Validate the batch.**
  `py audit/tools/harness.py validate` → exit 0.
- [ ] **Step 4: Status check.** `py audit/tools/audit_status.py --kind relic` —
  audited count = batch size, invalid 0.
- [ ] **Step 5: Harden the prompt.** Append to `audit/tools/PROMPT.md` (bump
  the version header) any bug class or procedure lesson the batch surfaced —
  e.g. a recurring C# idiom the checklist missed. If nothing surfaced, state
  that in the task report; do not pad the prompt.
- [ ] **Step 6: Full suite** (`py -m pytest test/ -q`) — audits add no code,
  so any failure means an accidental engine edit; revert it.
- [ ] **Step 7: Commit.**
  `git add audit/records/relic audit/tools/PROMPT.md audit/tools/name_overrides.json`
  then `git commit -m "audit(relic): pilot batch records"` (on
  `audit-pipeline` only).

---

### Tasks 12–16: Remaining content audits (repeat Task 11's procedure)

Each task repeats Task 11's Steps 1–7 verbatim with a different roster
slice; batch size 15 units (smaller for the final partial batch of each
kind). One task = one kind; within a task, run batches sequentially until
`py audit/tools/audit_status.py --kind <kind>` shows `unaudited 0`. Batches are
independent — if executing with subagents, one subagent per batch, each
given `audit/tools/PROMPT.md` plus its unit list.

| Task | Kind | Roster command | Notes |
|---|---|---|---|
| 12 | relic (remainder) | `py audit/tools/harness.py roster relic` | Includes event/Neow/Ancient-shrine pools; out-of-combat no-op stub relics get `waiver` verdicts naming the stubbed behavior |
| 13 | power | `py audit/tools/harness.py roster power` | Sign-aware typing (bug class 3) applies to every stack-amount power |
| 14 | monster | `py audit/tools/harness.py roster monster` | MachineMonster ports: compare graphs node-by-node against the C# AddState/AddBranch calls (bug class 6). Hand-rolled monsters (~18): the audit must reconstruct the equivalent graph from the C# and verify the hand-rolled `_move_key` logic emits identical move sequences for the reachable state space, or record a `gap` recommending a state-machine port |
| 15 | card | `py audit/tools/harness.py roster card` | Mostly numbers/keywords; verify upgrade (`+`) values too — sim models upgrades inside one class, C# may use fields or separate branches |
| 16 | event + enchantment | `py audit/tools/harness.py roster event` / `roster enchantment` | Combat-facing effects only; pure-UI event text is out of audit scope (waiver) |

Completion criterion for the whole plan:
`py audit/tools/audit_status.py --strict` exits 0 except for open `gap` records
(gaps are expected output, queued as follow-up fixes — each fix lands later
with its own failing-then-passing test and flips its record to `faithful`
on re-audit). Report the final table plus the list of open gaps.

---

## Execution notes

- **Order:** Tasks 1→2→3→4 are sequential (each consumes the previous).
  Tasks 5–10 depend on 2 (+4 for the trace helper) and are independent of
  each other. Tasks 11–16 depend on 2–3; 12–16 depend on 11's hardened
  prompt. Seam audits (5–10) before content batches (11–16), per the spec's
  order of attack.
- **Commits are branch-scoped:** commit each task on `audit-pipeline`; never push, never touch `main`. Perry reviews and merges the branch.
- Audits must not modify engine code. If an audit is blocked by ambiguity
  (decompilation artifact obscures semantics), record the ambiguity in the
  record's entry (`rationale`) per the spec's honest-limits section rather
  than guessing.
