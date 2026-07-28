"""Backfill `extra_sources` on the content audit records.

A content record pins exactly two files -- its unit's `game_source` and
`sim_source`. Its verdicts routinely rest on many more: `PowerCmd.cs`,
`cmds.py`, `combat.py`, `cards/base.py`, the sibling model whose behaviour a
dormancy argument turns on. Those citations carry line numbers and nothing
hashed them, so the record reported fresh while resting on text that could
change underneath it. audit/README.md, "Staleness": *every file a verdict cites
with a line number must be hashed by the record.*

This tool mechanises that rule. Per record it

  1. extracts every `path:line` citation from every string in the record
     (values AND keys -- hook keys carry provenance like
     `"Type (inherited, TemporaryStrengthPower.cs:32-42)"`),
  2. resolves each to a real file -- `.cs` under the game root, `.py` under the
     repo root -- and DISCARDS anything that does not,
  3. skips whatever the singular `game_source`/`sim_source` pair already pins,
  4. writes the rest to `extra_sources` with a fresh sha256 and the right
     `side`.

It is idempotent: an entry already in `extra_sources` is left exactly as it is,
never re-hashed. Re-pinning a hash is `harness.py rehash`'s job and is not a
re-audit -- see the banner that command prints.

It reports rather than silently drops. A citation that resolves to nothing is
either a typo or a stale path and both are findings; so is a citation whose
line number is past the end of the file it names. Both are printed and neither
is written.

  py audit/tools/backfill_sources.py                    # every content record
  py audit/tools/backfill_sources.py --kind power       # one kind
  py audit/tools/backfill_sources.py --dry-run          # report, write nothing
  py audit/tools/backfill_sources.py --verbose          # a line per record
  py audit/tools/backfill_sources.py audit/records/card/anger.json  # by path

Seam records are skipped: they already use the plural `game_sources` /
`sim_sources` lists and pin their evidence through `SEAM_SOURCES`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# audit/tools/backfill_sources.py -> parents[0]=audit/tools, [1]=audit,
# [2]=repo root. Mirrors harness.py so `audit.tools` imports as a package.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools import harness

# `Foo.cs:120`, `src/Core/Commands/PowerCmd.cs:236-241`, `cards/base.py:65`,
# `sts2_rl\powers.py:3497`. The lookbehind stops a match starting mid-path, and
# the line number is REQUIRED: the staleness rule is about citations that pin a
# line, and a bare `py audit/tools/power_census.py slots` is a command, not
# evidence. A trailing range (`-241`) is left to the caller to ignore.
CITATION_RE = re.compile(r"(?<![\w./\\-])([A-Za-z_][\w./\\+-]*\.(?:cs|py)):(\d+)")

# Sim citations are written relative to the sim package about as often as they
# are written from the repo root (`powers.py:3497`, `cards/base.py:65`), so the
# repo root and this prefix are both tried before the basename index.
SIM_PREFIX = "sts2_rl"

# Never pinned, and PRUNED when found -- the pipeline's own machinery and its
# pins.  This mirrors `citation_check._NEVER_HASHED` verbatim, and until
# 2026-07-27 the two tools contradicted each other: citation_check declined to
# demand these, and this tool pinned them anyway, 28 of them.  The contradiction
# had a cost.  A record that hashes `test/test_hook_order.py` goes stale every
# time ANY pin is added anywhere in that file -- appending the four potion pins
# staled nine card and relic records whose own cited lines had not moved by a
# byte -- and a record hashing `audit/tools/relic_probes.py` goes stale when a
# probe is edited.  Neither is a fact about the audited unit, so neither is a
# verdict that needs re-checking; and citation_check's rationale for the
# exclusion is the right one ("a broken pin fails loudly on its own").
#
# Pruning removes a hash that should never have been written; it changes no
# verdict text and no line citation, so the record still SAYS it rests on the
# pin and the pin still has to pass.
_NEVER_HASHED = ("audit/tools/", "test/")


def _never_hashed(rel: str) -> bool:
    return rel.replace("\\", "/").startswith(_NEVER_HASHED)


_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache",
              ".venv", "venv", "env", "node_modules", "build", "dist"}


def walk_strings(obj):
    """Every string anywhere in a record, dict KEYS included."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def citations(record: dict) -> dict[str, set[int]]:
    """cited path (separators normalised to `/`) -> the line numbers cited."""
    out: dict[str, set[int]] = defaultdict(set)
    for text in walk_strings(record):
        for m in CITATION_RE.finditer(text):
            out[m.group(1).replace("\\", "/")].add(int(m.group(2)))
    return dict(out)


class Resolver:
    """Turns a cited path into a real file under one of the two roots."""

    def __init__(self, game_root: Path | None = None):
        self.game_root = Path(game_root or harness.DEFAULT_GAME_ROOT)
        self._idx: dict[str, dict[str, list[Path]]] = {}
        self._lines: dict[Path, int] = {}

    def _index(self, side: str) -> dict[str, list[Path]]:
        """filename -> every file with that name under the side's root.

        Most citations are a bare filename (`PowerCmd.cs`), which is only
        resolvable by search."""
        if side not in self._idx:
            root = self.game_root if side == "game" else _REPO
            pattern = "*.cs" if side == "game" else "*.py"
            idx: dict[str, list[Path]] = defaultdict(list)
            for p in root.rglob(pattern):
                if _SKIP_DIRS.isdisjoint(p.parts):
                    idx[p.name].append(p)
            self._idx[side] = dict(idx)
        return self._idx[side]

    def line_count(self, path: Path) -> int:
        if path not in self._lines:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            self._lines[path] = text.count("\n") + (0 if text.endswith("\n") else 1)
        return self._lines[path]

    def resolve(self, raw: str, max_line: int, kind: str,
                prefer: Path | None) -> tuple[Path | None, str, str]:
        """(file or None, side, how).

        `how` is one of `exact` (the path resolves as written), `basename` (a
        bare filename found by search), `mispathed` (a directory-qualified path
        that does NOT exist as written but whose basename is unique -- a finding
        worth reporting, e.g. the seam tier's `Modifiers/Flight.cs` whose real
        path is `Models/Modifiers/Flight.cs`), `ambiguous` or `missing`."""
        side = "game" if raw.endswith(".cs") else "sim"
        if side == "game":
            if (self.game_root / raw).is_file():
                return self.game_root / raw, side, "exact"
        else:
            for prefix in ("", SIM_PREFIX):
                cand = _REPO / prefix / raw if prefix else _REPO / raw
                if cand.is_file():
                    return cand, side, "exact"

        qualified = "/" in raw
        cands = list(self._index(side).get(raw.rsplit("/", 1)[-1], ()))
        if qualified:
            suffix = os.path.normcase(raw.replace("/", os.sep))
            narrowed = [c for c in cands
                        if os.path.normcase(str(c)).endswith(suffix)]
            cands = narrowed or cands
        cands = self._disambiguate(cands, max_line, kind, side, prefer)
        if len(cands) == 1:
            return cands[0], side, ("mispathed" if qualified else "basename")
        return None, side, ("ambiguous" if cands else "missing")

    def _disambiguate(self, cands: list[Path], max_line: int, kind: str,
                      side: str, prefer: Path | None) -> list[Path]:
        """Two same-named C# files exist in this source (`LostWisp.cs` is both
        an event and a relic; `PaelsLegion.cs` both a monster and a relic), so
        a bare citation of one is genuinely ambiguous. Narrow it with facts the
        citation itself carries, never a guess: the cited LINE has to exist in
        the file, the record's own unit file wins outright, and a record of
        kind K prefers K's model directory."""
        if len(cands) <= 1:
            return cands
        long_enough = [c for c in cands if self.line_count(c) >= max_line]
        cands = long_enough or cands
        if prefer is not None:
            same = [c for c in cands if _same_file(c, prefer)]
            if same:
                return same[:1]
        if side == "game" and kind in harness.GAME_MODEL_DIRS:
            model_dir = os.path.normcase(
                str(self.game_root / harness.GAME_MODEL_DIRS[kind]))
            in_kind = [c for c in cands
                       if os.path.normcase(str(c.parent)) == model_dir]
            if len(in_kind) == 1:
                return in_kind
        return cands


def _same_file(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _rel(path: Path, side: str, game_root: Path) -> str:
    """Store the entry path relative to the root its `side` names, with
    forward slashes -- the form audit/README.md's example uses, and the only
    form that also resolves off Windows."""
    base = game_root if side == "game" else _REPO
    return path.resolve().relative_to(base.resolve()).as_posix()


def _own_sources(record: dict, game_root: Path) -> dict[str, Path]:
    """The absolute files the record's singular pair already pins."""
    out: dict[str, Path] = {}
    for key, base in (("game_source", game_root), ("sim_source", _REPO)):
        src = record.get(key)
        if isinstance(src, dict) and src.get("path"):
            p = base / src["path"]
            if p.is_file():
                out[key] = p
    return out


def _insert_extra_sources(record: dict, entries: list[dict]) -> dict:
    """Rebuild the record with `extra_sources` sitting after `sim_source`."""
    if "extra_sources" in record:
        record["extra_sources"] = entries
        return record
    out: dict = {}
    for key, value in record.items():
        out[key] = value
        if key == "sim_source":
            out["extra_sources"] = entries
    if "extra_sources" not in out:
        out["extra_sources"] = entries
    return out


def backfill_record(path: Path, resolver: Resolver, write: bool = True,
                    prune: bool = False, add: bool = True) -> dict:
    """Backfill one record. Returns a per-record stats dict; writes only when
    something was actually added (or pruned)."""
    record = json.loads(path.read_text(encoding="utf-8"))
    unit = record.get("unit", "")
    kind = unit.partition("/")[0]
    stats = {
        "unit": unit or f"?/{path.stem}", "cited": 0, "resolved": 0,
        "covered": 0, "already": 0, "added": 0, "unresolved": [],
        "mispathed": [], "past_eof": [], "changed": False,
        "pruned": 0, "pruned_paths": [],
    }
    if kind == "seam":
        stats["skipped"] = "seam record -- uses the plural source lists"
        return stats

    own = _own_sources(record, resolver.game_root)
    covered = [p for p in own.values()]
    existing = list(record.get("extra_sources") or [])
    if prune:
        kept = [e for e in existing
                if not (isinstance(e, dict) and e.get("path")
                        and _never_hashed(str(e["path"])))]
        stats["pruned"] = len(existing) - len(kept)
        if stats["pruned"]:
            stats["pruned_paths"] = [
                str(e["path"]).replace("\\", "/") for e in existing
                if isinstance(e, dict) and e.get("path")
                and _never_hashed(str(e["path"]))
            ]
            existing = kept
            record["extra_sources"] = existing
            stats["changed"] = True
    have: list[Path] = []
    for entry in existing:
        if isinstance(entry, dict) and entry.get("path"):
            p = harness.source_base(entry.get("side"), resolver.game_root) / entry["path"]
            have.append(p)
    prefer = own.get("game_source")

    additions: list[dict] = []
    seen: list[Path] = []
    for raw, lines in sorted(citations(record).items()):
        stats["cited"] += 1
        target, side, how = resolver.resolve(raw, max(lines), kind, prefer)
        if target is None:
            stats["unresolved"].append((raw, how))
            continue
        stats["resolved"] += 1
        if how == "mispathed":
            stats["mispathed"].append((raw, _rel(target, side, resolver.game_root)))
        over = [n for n in sorted(lines) if n > resolver.line_count(target)]
        if over:
            stats["past_eof"].append(
                (raw, over, resolver.line_count(target)))
        if any(_same_file(target, c) for c in covered):
            stats["covered"] += 1
            continue
        if any(_same_file(target, h) for h in have):
            stats["already"] += 1
            continue
        if any(_same_file(target, s) for s in seen):
            continue
        rel = _rel(target, side, resolver.game_root)
        if _never_hashed(rel):
            # The pipeline's own machinery and its pins -- see _NEVER_HASHED.
            stats["skipped_never_hashed"] = (
                stats.get("skipped_never_hashed", 0) + 1)
            continue
        seen.append(target)
        additions.append({
            "path": rel,
            "sha256": harness.file_sha256(target),
            "side": side,
        })

    if not add:
        additions = []
    stats["added"] = len(additions)
    if additions:
        additions.sort(key=lambda e: (e["side"], e["path"]))
        record = _insert_extra_sources(record, existing + additions)
        stats["changed"] = True
    elif stats["pruned"]:
        record = _insert_extra_sources(record, existing)
    if stats["changed"] and write:
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return stats


def _targets(args) -> list[Path]:
    adir = Path(harness.DEFAULT_AUDITS_DIR)
    if args.paths:
        return [Path(p) for p in args.paths]
    if args.kind:
        return sorted((adir / args.kind).glob("*.json"))
    return [p for p in sorted(adir.rglob("*.json")) if p.parent.name != "seam"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="record files (default: every "
                                             "content record)")
    ap.add_argument("--kind", choices=sorted(harness.GAME_MODEL_DIRS),
                    help="every record of one kind")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be added, write nothing")
    ap.add_argument("--verbose", action="store_true",
                    help="one line per record instead of only the totals")
    ap.add_argument("--prune", action="store_true",
                    help="also REMOVE extra_sources entries under the "
                         "_NEVER_HASHED prefixes (audit/tools/, test/) that an "
                         "earlier run pinned; they cause false staleness "
                         "whenever a pin or a probe is edited")
    ap.add_argument("--no-add", action="store_true",
                    help="do not add anything; report only, or prune only when "
                         "combined with --prune. Use this to make a prune a "
                         "surgical change instead of a tree-wide backfill")
    args = ap.parse_args(argv)

    resolver = Resolver()
    rows = [backfill_record(p, resolver, write=not args.dry_run,
                            prune=args.prune, add=not args.no_add)
            for p in _targets(args)]
    rows = [r for r in rows if "skipped" not in r]

    totals = {k: sum(r[k] for r in rows)
              for k in ("cited", "resolved", "covered", "already", "added",
                        "pruned")}
    changed = sum(1 for r in rows if r["changed"])

    if args.verbose:
        for r in sorted(rows, key=lambda r: r["unit"]):
            print(f"{r['unit']:<34} cited={r['cited']:<4} resolved={r['resolved']:<4}"
                  f" covered={r['covered']:<3} already={r['already']:<3}"
                  f" added={r['added']:<3}"
                  f" unresolved={len(r['unresolved'])}")

    unresolved: dict[tuple[str, str], list[str]] = defaultdict(list)
    mispathed: dict[tuple[str, str], list[str]] = defaultdict(list)
    past_eof: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for raw, how in r["unresolved"]:
            unresolved[(raw, how)].append(r["unit"])
        for raw, real in r["mispathed"]:
            mispathed[(raw, real)].append(r["unit"])
        for raw, over, total in r["past_eof"]:
            past_eof[f"{raw}:{','.join(map(str, over))} (file has {total} lines)"
                     ].append(r["unit"])

    if mispathed:
        print(f"\nMISPATHED -- resolved by basename, the cited path does not "
              f"exist as written ({len(mispathed)} distinct):")
        for (raw, real), units in sorted(mispathed.items()):
            print(f"  {raw} -> {real}   [{len(units)}] {', '.join(units[:4])}")
    if past_eof:
        shown = sorted(past_eof.items())
        print(f"\nCITED PAST END OF FILE -- advisory. The file exists and is "
              f"pinned; the LINE does not exist, so the citation was written "
              f"against different text ({len(shown)} distinct):")
        for cite, units in (shown if args.verbose else shown[:12]):
            print(f"  {cite}   [{len(units)}] {', '.join(units[:4])}")
        if not args.verbose and len(shown) > 12:
            print(f"  ... {len(shown) - 12} more (--verbose for all)")
    if unresolved:
        print(f"\nUNRESOLVABLE -- discarded, not pinned ({len(unresolved)} "
              f"distinct paths):")
        for (raw, how), units in sorted(unresolved.items()):
            print(f"  {raw}  [{how}]   cited by {len(units)}: "
                  f"{', '.join(units[:6])}")

    verb = "would add" if args.dry_run else "added"
    print(f"\n{len(rows)} content record(s): "
          f"{totals['cited']} citation(s) found, {totals['resolved']} resolved, "
          f"{totals['covered']} already covered by the singular pair, "
          f"{totals['already']} already in extra_sources, "
          f"{sum(len(r['unresolved']) for r in rows)} unresolvable")
    print(f"{verb} {totals['added']} extra_sources entr(ies) across "
          f"{changed} record(s)")
    skipped = sum(r.get("skipped_never_hashed", 0) for r in rows)
    if skipped:
        print(f"skipped {skipped} citation(s) under {_NEVER_HASHED} "
              f"(the pipeline's own machinery and its pins -- see "
              f"_NEVER_HASHED)")
    if args.prune:
        pruned_by = {}
        for r in rows:
            for p in r.get("pruned_paths", []):
                pruned_by.setdefault(p, []).append(r["unit"])
        pverb = "would prune" if args.dry_run else "PRUNED"
        print(f"{pverb} {totals['pruned']} previously-pinned entr(ies) under "
              f"{_NEVER_HASHED}:")
        for p, units in sorted(pruned_by.items()):
            print(f"  {p}   [{len(units)}] {', '.join(sorted(units))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
