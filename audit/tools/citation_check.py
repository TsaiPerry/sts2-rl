"""Mechanical citation check for audit records.

The audit contract's binding rules 7 and 8 exist because agents cite files that
do not exist and line numbers that do not: "two successive agents invented a
test class that does not exist", and three consecutive seam tasks shipped
`file:line` citations the record never hashed. The seam tier caught those by
hand-sweeping each record. That does not scale to fifteen parallel content
batches, so this does it mechanically.

For every `audit/records/**/*.json`, extract every source citation in the record's
free text -- `some/path.py:123`, `SomeFile.cs:45-67`, bare `Foo.cs` -- resolve
it against the sim repo and the game root, and report:

  MISSING     the cited path does not exist on either side
  OUT-OF-RANGE the line number is past the end of the file
  UNHASHED    the citation resolves, but the record does not hash that file
              (rule 7 wants this stated in the rationale, so this is a
              REMINDER, not a failure -- see --strict)

It never judges whether a citation is *apt*; only whether it is real. A green
run means nobody invented a path or a line number.

  py audit/tools/citation_check.py                 # every record
  py audit/tools/citation_check.py audit/records/relic    # one kind
  py audit/tools/citation_check.py --strict        # UNHASHED also fails
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools.harness import DEFAULT_AUDITS_DIR, DEFAULT_GAME_ROOT  # noqa: E402

# `path/to/File.cs:12`, `sts2_rl/relics/x.py:3-9`, or a bare `File.cs`.
# The path part allows the separators the records actually use (both slashes).
_CITE = re.compile(
    r"(?<![\w/\\.])"
    r"((?:[\w.\-]+[/\\])*[\w.\-]+\.(?:cs|py))"      # path
    r"(?::(\d+)(?:\s*[-–]\s*(\d+))?)?"         # :line or :line-line
)

# Cited but deliberately not hashed by any record: the pipeline's own machinery
# and its pins. Documented in docs/audit/seams/hook_dispatch.md's fix-pass
# section -- hashing the harness would make every record stale whenever any
# source list changes, and a broken pin fails loudly on its own.
_NEVER_HASHED = ("audit/tools/", "test/")


def _iter_text(record: dict):
    """Every free-text field a citation can hide in."""
    for entry in list((record.get("hooks") or {}).values()) \
            + (record.get("guards") or []) + (record.get("steps") or []):
        for key in ("maps_to", "rationale", "issue", "what"):
            if entry.get(key):
                yield entry[key]


def _hashed_paths(record: dict) -> set[str]:
    """Every path this record actually hashes, in all THREE shapes.

    ``extra_sources`` was missing here until 2026-07-27 and it is the shape
    that matters most: the singular ``game_source``/``sim_source`` pair only
    ever covers a content record's own two files, and audit/README.md's
    Staleness section makes ``extra_sources`` the sanctioned home for every
    other file a verdict cites -- which ``backfill_sources.py`` exists to
    populate. Omitting it made UNHASHED report the exact citations the
    pipeline had just pinned on purpose: 315 of the potion tier's 1035, and
    every content record written since ``extra_sources`` landed. The count
    over-reported, so nothing was ever falsely cleared, but ``--strict`` was
    unusable on any record that used the mechanism it is supposed to enforce.
    """
    out = set()
    for key in ("game_source", "sim_source"):
        src = record.get(key)
        if src and src.get("path"):
            out.add(src["path"].replace("\\", "/"))
    for key in ("game_sources", "sim_sources"):
        for src in record.get(key) or []:
            if src.get("path"):
                out.add(src["path"].replace("\\", "/"))
    # `extra_sources` entries are mixed game/sim and each names its own root in
    # a `side` field, but the paths this set is compared against are already
    # root-relative on both sides (see `check`), so the side is not needed to
    # match -- only to resolve, which `_resolve` does from the roots directly.
    for src in record.get("extra_sources") or []:
        if isinstance(src, dict) and src.get("path"):
            out.add(str(src["path"]).replace("\\", "/"))
    return out


def _own_paths(record: dict) -> set[str]:
    """Just the unit's OWN two files -- the singular pair.

    Kept apart from `_hashed_paths` because it is the tie-breaker for a bare
    basename: a record hashes its own `Relics/Byrdpip.cs` AND, through
    `extra_sources`, the unrelated `Monsters/Byrdpip.cs` it cites for
    contrast, so once `extra_sources` joined the hashed set (2026-07-27) a bare
    `Byrdpip.cs:72` had two candidates and got reported ambiguous. The
    docstring of `_resolve` already states the right rule -- "a record citing a
    bare basename almost always means its own unit's file" -- so the singular
    pair wins outright and ambiguity is reported only when it does not settle
    it.
    """
    out = set()
    for key in ("game_source", "sim_source"):
        src = record.get(key)
        if src and src.get("path"):
            out.add(src["path"].replace("\\", "/"))
    return out


def _resolve(path: str, hashed: set[str],
             own: set[str] | None = None) -> tuple[Path | None, str, bool]:
    """Find the cited file under the sim repo or the game root.

    Returns (path, label, ambiguous). `hashed` is the record's own hashed
    source list and is consulted FIRST for bare basenames: the game ships two
    `Byrdpip.cs` (a 32-line Monsters one and a 73-line Relics one), and a
    naive rglob picked the monster, reporting a correct `Byrdpip.cs:69-72`
    citation as out of range. A record citing a bare basename almost always
    means its own unit's file, so prefer that -- and `own`, the singular
    game_source/sim_source pair, is what "its own unit's file" means when the
    hashed set holds more than one candidate.
    """
    own = own or set()
    norm = path.replace("\\", "/")
    for root, label in ((_REPO, "sim"), (DEFAULT_GAME_ROOT, "game")):
        cand = root / norm
        if cand.is_file():
            return cand, label, False
    name = norm.rsplit("/", 1)[-1]
    # (a) the record's own hashed sources.
    #
    # Iterate SORTED and collect EVERY match. `hashed` is a set, so returning
    # the first hit made this whole gate nondeterministic: a record hashing both
    # `monsters/base.py` and `cards/base.py` resolved a bare `base.py:269`
    # against whichever the set happened to yield first, and the reported
    # OUT-OF-RANGE count flipped between 0 and 3 on byte-identical records
    # purely with PYTHONHASHSEED. Every "OUT-OF-RANGE 0" this gate printed
    # before this fix was true only of the seed that ran. Found by batch 17.
    #
    # More than one match is genuine ambiguity and must be reported as such,
    # not silently resolved -- the same mistake the (b) branch below already
    # got right.
    hits = [rel for rel in sorted(hashed)
            if rel.rsplit("/", 1)[-1] == name]
    found = []
    for rel in hits:
        for root, label in ((_REPO, "sim"), (DEFAULT_GAME_ROOT, "game")):
            cand = root / rel
            if cand.is_file():
                found.append((cand, label, rel in own))
                break
    if len(found) == 1:
        return found[0][0], found[0][1], False
    if len(found) > 1:
        # The unit's own file settles it; two `extra_sources` candidates with
        # the same basename and no own-file among them stay ambiguous.
        mine = [f for f in found if f[2]]
        if len(mine) == 1:
            return mine[0][0], mine[0][1], False
        return found[0][0], found[0][1], True
    # (b) fall back to a tree search, and SAY SO when it is ambiguous
    #
    # `audit/tools` is where the probes live since the audits/ -> audit/records/
    # restructure; `tools` is kept because the pre-restructure records cite bare
    # probe basenames that used to resolve under it. Dropping `tools` from this
    # list without adding `audit/tools` is exactly what turned 26 correct relic
    # citations into MISSING when the relic tier was merged.
    roots = ((_REPO / "sts2_rl", "sim"), (_REPO / "audit" / "tools", "sim"),
             (_REPO / "tools", "sim"),
             (_REPO / "test", "sim"), (DEFAULT_GAME_ROOT / "src", "game"))
    for root, label in roots:
        if not root.is_dir():
            continue
        hits = list(root.rglob(name))
        if hits:
            return hits[0], label, len(hits) > 1
    return None, "", False


def check(paths: list[Path], strict: bool = False) -> int:
    missing: list[str] = []
    oor: list[str] = []
    ambig: list[str] = []
    unhashed: set[tuple[str, str]] = set()
    unhashed_bare: set[tuple[str, str]] = set()
    seen = 0

    for rec_path in paths:
        record = json.loads(rec_path.read_text(encoding="utf-8"))
        unit = record.get("unit", rec_path.stem)
        hashed = _hashed_paths(record)
        own = _own_paths(record)
        cited: dict[str, int] = {}
        for text in _iter_text(record):
            for m in _CITE.finditer(text):
                path, lo, hi = m.group(1), m.group(2), m.group(3)
                line = int(hi or lo) if (lo or hi) else 0
                cited[path] = max(cited.get(path, 0), line)
        for path, line in sorted(cited.items()):
            seen += 1
            resolved, label, ambiguous = _resolve(path, hashed, own)
            if resolved is None:
                missing.append(f"{unit}: cited path does not exist: {path}")
                continue
            if line:
                n = len(resolved.read_text(encoding="utf-8-sig",
                                           errors="replace").splitlines())
                if line > n:
                    # Never fail on a basename that matched several files --
                    # the citation may be right about a different one.
                    (ambig if ambiguous else oor).append(
                        f"{unit}: {path}:{line} but "
                        f"{resolved.relative_to(_REPO if label == 'sim' else DEFAULT_GAME_ROOT)}"
                        f" has {n} lines")
            rel = str(resolved.relative_to(
                _REPO if label.startswith("sim") else DEFAULT_GAME_ROOT)
            ).replace("\\", "/")
            if rel not in hashed and not rel.startswith(_NEVER_HASHED):
                # Binding rule 7 is scoped to citations that carry a LINE
                # NUMBER ("Every file you cite with a line number must be
                # hashed by the record"), and `backfill_sources.py`'s
                # CITATION_RE requires one for the same reason -- a bare
                # `SpeedPotion.cs` in a prose comparison pins nothing and
                # cannot go stale in a way that invalidates a verdict. Keeping
                # both sets, but only the line-numbered one is a rule-7
                # finding, is what makes --strict usable.
                (unhashed if line else unhashed_bare).add((unit, rel))

    print(f"{len(paths)} record(s), {seen} citation(s) checked")
    for label, rows in (("MISSING", missing), ("OUT-OF-RANGE", oor),
                        ("AMBIGUOUS BASENAME (not a failure -- several files share the name)", ambig)):
        print(f"\n{label}: {len(rows)}")
        for row in rows:
            print(f"  {row}")
    print(f"\nUNHASHED, cited WITH a line number (binding rule 7 -- pin these "
          f"in extra_sources or name them in the rationale): {len(unhashed)}")
    for unit, rel in sorted(unhashed):
        print(f"  {unit}: {rel}")
    print(f"\nUNHASHED, cited as a bare filename (advisory, outside rule 7 -- "
          f"no line is pinned, so it cannot go stale): {len(unhashed_bare)}")
    for unit, rel in sorted(unhashed_bare):
        print(f"  {unit}: {rel}")

    bad = len(missing) + len(oor) + (len(unhashed) if strict else 0)
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="record files or directories")
    ap.add_argument("--strict", action="store_true",
                    help="treat UNHASHED citations as failures too")
    args = ap.parse_args(argv)
    roots = [Path(p) for p in args.paths] or [DEFAULT_AUDITS_DIR]
    files: list[Path] = []
    for r in roots:
        files.extend(sorted(r.rglob("*.json")) if r.is_dir() else [r])
    return check(files, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
