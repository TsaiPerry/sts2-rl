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

# audit/tools/audit_status.py -> parents[0]=audit/tools, [1]=audit, [2]=repo
# root. The repo root has to be on sys.path BEFORE the `audit.tools` import
# below, because running this file as a script puts audit/tools on sys.path
# and not the root the `audit` namespace package lives under.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools import harness


def _is_stale(record: dict, unit: str, game_root: Path) -> bool:
    def drifted(src: dict, base: Path) -> bool:
        p = base / src.get("path", "")
        return (not p.is_file()) or harness.file_sha256(p) != src.get("sha256")

    # Every record shape can carry `extra_sources`: the files a verdict cites
    # beyond the unit's own two. Without this a content record's citations of
    # PowerCmd.cs / cmds.py / combat.py go unpinned, and the record reports
    # fresh while resting on line numbers nothing hashes.
    if any(drifted(s, harness.source_base(s.get("side"), game_root))
           for s in record.get("extra_sources") or []):
        return True

    if unit.startswith("seam/"):
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
                 "stale": 0, "gaps": 0, "live": 0, "unaudited": []}
        for unit in units:
            path = adir / kind / (unit.split("/", 1)[1] + ".json")
            if not path.is_file():
                stats["unaudited"].append(unit)
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                stats["invalid"] += 1
                continue
            if record.get("unit") != unit:
                stats["invalid"] += 1
                continue
            errs = harness.validate_record(record, game_root=root)
            if errs:
                stats["invalid"] += 1
                continue
            stats["audited"] += 1
            if _is_stale(record, unit, root):
                stats["stale"] += 1
            if record.get("verdict") == "gap":
                stats["gaps"] += 1
            # `live` counts records carrying at least one gap entry explicitly
            # marked live: true. It reads low until records adopt the key —
            # absence is "not stated", not "dormant".
            if any(e.get("live") is True for e in harness.record_entries(record)):
                stats["live"] += 1
        out[kind] = stats
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on stale, gaps, or unaudited units")
    ap.add_argument("--kind", choices=tuple(sorted(harness.GAME_MODEL_DIRS)) + ("seam",))
    args = ap.parse_args(argv)

    stats = collect(kinds=(args.kind,) if args.kind else None,
                     game_root=harness.DEFAULT_GAME_ROOT,
                     audits_dir=harness.DEFAULT_AUDITS_DIR)
    invalid = stale = gaps = unaudited = 0
    print(f"{'kind':<12}{'total':>6}{'audited':>9}{'invalid':>9}"
          f"{'stale':>7}{'gaps':>6}{'live':>6}{'unaudited':>11}")
    for kind, s in stats.items():
        print(f"{kind:<12}{s['total']:>6}{s['audited']:>9}{s['invalid']:>9}"
              f"{s['stale']:>7}{s['gaps']:>6}{s['live']:>6}"
              f"{len(s['unaudited']):>11}")
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
