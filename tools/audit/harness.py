"""Completeness harness for the source-to-sim audit pipeline.

Design: docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md.
Deliberately dumb — enumeration, hashing, and record validation only; it
never judges faithfulness. Agents write the audit records; this tool makes
sure they cannot skip a unit, skip a hook, or leave a verdict vague.

Usage:
  py tools/audit/harness.py roster [KIND]       # work queue + unmatched units
  py tools/audit/harness.py skeleton UNIT       # write record skeleton
  py tools/audit/harness.py validate [PATH...]  # validate records
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


# ── Seams (Tier 2) ────────────────────────────────────────────────────────
# Engine seams audited as ordering specs, not per-hook records. Paths are
# repo-relative (game side under the game root). If a listed C# file does
# not exist, locate the real one with a grep and fix this table.
SEAM_SOURCES: dict[str, tuple[list[str], list[str]]] = {
    "damage_pipeline": (
        # DamageCmd.cs itself is just two AttackCommand-builder factory
        # methods; the actual per-hit pipeline (block/modifier/kill order)
        # lives in CreatureCmd.Damage, dispatched through the Hook static
        # methods it calls (ModifyDamage, ModifyHpLost, ShouldDie, ...).
        ["src/Core/Commands/DamageCmd.cs", "src/Core/Commands/CreatureCmd.cs",
         "src/Core/Hooks/Hook.cs"],
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
        ["src/Core/MonsterMoves/MonsterMoveStateMachine/MonsterMoveStateMachine.cs"],
        ["sts2_rl/monsters/state_machine.py"],
    ),
}
SEAMS: tuple[str, ...] = tuple(SEAM_SOURCES)


def _hash_sources(paths: list[str], base: Path) -> list[dict]:
    return [{"path": p, "sha256": file_sha256(base / p)} for p in paths]


def skeleton(unit: str, game_root: Path | None = None,
             audits_dir: Path | None = None) -> Path:
    """Write audits/<kind>/<id>.json with hooks/steps enumerated and
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_roster = sub.add_parser("roster", help="print the audit work queue")
    ap_roster.add_argument("kind", nargs="?", choices=sorted(GAME_MODEL_DIRS))
    ap_skel = sub.add_parser("skeleton", help="write a record skeleton")
    ap_skel.add_argument("unit", help="e.g. relic/unsettling_lamp or seam/power_cmd")
    ap_val = sub.add_parser("validate", help="validate audit records")
    ap_val.add_argument("paths", nargs="*", help="record files (default: all)")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
