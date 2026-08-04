r"""Classify stale audit records for the 2026-08-03 stale sweep.

Class (a): the record's hash went stale but every file:line citation it
carries is BYTE-IDENTICAL at the SAME line numbers in the current tree —
the pin-append precedent (README 'The 28 entries...') generalized. These get
the fast re-audit: verify receipt, then `harness.py rehash <unit>`.
Class (b): any span changed, moved, or the hashed historical text cannot be
recovered from git — full agent re-audit.

Usage: py audit/tools/stale_triage.py [--kind relic] [--out audit/stale-sweep/receipts.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# --- reuse the harness's normalization + staleness, and citation_check's
# citation regex + record walking, via importlib (audit/tools is not a
# package with an __init__.py, so a plain `from audit.tools import harness`
# only works by namespace-package luck; importlib.util is explicit and
# matches the loader the brief and gap_queue.py use). ---
import importlib.util


def _load(name):
    p = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


harness = _load("harness")                  # normalize/hash + roster helpers
citation_check = _load("citation_check")     # citation regex + _NEVER_HASHED
audit_status = _load("audit_status")         # _is_stale, the same staleness rule


def span_identical(old_text: str, new_text: str, lo: int, hi: int) -> bool:
    """Lines lo..hi (1-based, inclusive) byte-identical at the same numbers."""
    old = old_text.splitlines()
    new = new_text.splitlines()
    if hi > len(old) or hi > len(new):
        return False
    return old[lo - 1:hi] == new[lo - 1:hi]


def harness_normalized_sha(text: str) -> str:
    """The exact normalization harness.file_sha256 hashes a file's text with,
    applied here to text pulled from git rather than from disk."""
    import hashlib
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


_BLOB_CACHE: dict[tuple[str, str], str | None] = {}


def historical_text(path: str, want_sha: str) -> str | None:
    """Recover the file text a record's sha256 was computed over, by walking
    this path's git history and hashing each blob with the harness's own
    normalization. None if no commit matches (uncommitted state -> class b)."""
    key = (path, want_sha)
    if key in _BLOB_CACHE:
        return _BLOB_CACHE[key]
    revs = subprocess.run(
        ["git", "rev-list", "HEAD", "--", path],
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace").stdout.split()
    found = None
    for rev in revs:
        show = subprocess.run(["git", "show", f"{rev}:{path}"],
                              cwd=REPO, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if show.returncode != 0:
            continue
        if harness_normalized_sha(show.stdout) == want_sha:
            found = show.stdout
            break
    _BLOB_CACHE[key] = found
    return found


_CURRENT_CACHE: dict[str, str | None] = {}


def current_text(path: str, base: Path) -> str | None:
    """Current on-disk text of `path` resolved against `base`, or None if
    missing. Cached per resolved path so repeated citations to the same file
    (e.g. cmds.py cited by dozens of records) read it once."""
    key = str(base / path)
    if key in _CURRENT_CACHE:
        return _CURRENT_CACHE[key]
    p = base / path
    text = None
    if p.is_file():
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    _CURRENT_CACHE[key] = text
    return text


def _all_source_entries(rec: dict) -> list[tuple[str, str, str]]:
    """Every (path, sha256, side) this record hashes, across all three shapes."""
    out: list[tuple[str, str, str]] = []
    for key, side in (("game_source", "game"), ("sim_source", "sim")):
        src = rec.get(key)
        if src and src.get("path"):
            out.append((src["path"].replace("\\", "/"), src.get("sha256", ""), side))
    for key, side in (("game_sources", "game"), ("sim_sources", "sim")):
        for src in rec.get(key) or []:
            if src.get("path"):
                out.append((src["path"].replace("\\", "/"), src.get("sha256", ""), side))
    for src in rec.get("extra_sources") or []:
        if isinstance(src, dict) and src.get("path"):
            out.append((str(src["path"]).replace("\\", "/"), src.get("sha256", ""),
                        src.get("side", "sim")))
    return out


def _raw_citations(rec: dict) -> list[tuple[str, int, int]]:
    """Every LINE-bearing citation `(raw_path, lo, hi)` in the record's free
    text, as literally written. A bare `file.py` with no line number is
    outside binding rule 7 (citation_check's own `unhashed_bare` split) and is
    not collected here — it cannot go stale in a way that invalidates a
    verdict, so it is not this triage's business either."""
    out: list[tuple[str, int, int]] = []
    for text in citation_check._iter_text(rec):
        for m in citation_check._CITE.finditer(text):
            path, lo, hi = m.group(1), m.group(2), m.group(3)
            if not lo:
                continue
            out.append((path.replace("\\", "/"), int(lo), int(hi) if hi else int(lo)))
    return out


def _resolve_citations(rec: dict) -> tuple[dict[str, list[tuple[int, int]]], list[str]]:
    """Resolve every raw citation against the record's OWN hashed set, using
    the same basename-fallback rule `citation_check._resolve` applies (a bare
    `aggression.py` in prose almost always means the unit's own hashed
    `sts2_rl/cards/aggression.py`) — but purely against the hashed/own sets,
    with no filesystem lookup, so this stays testable via the dependency-
    injected `historical`/`current` callables without a real checkout on
    disk (see test/test_stale_triage.py, whose fixture records name files
    that do not exist under the real repo/game roots at all).

    Returns (`rel_path -> spans`, `problem_reasons`) — a citation with no
    match in the hashed set, or an unresolved basename tie, goes in the
    reasons list instead of a spans bucket: either means class (b), the
    former because it is a straight rule-7 violation, the latter because an
    unresolved ambiguity cannot be proven byte-identical to anything."""
    hashed = citation_check._hashed_paths(rec)
    own = citation_check._own_paths(rec)
    groups: dict[str, list[tuple[int, int]]] = {}
    reasons: list[str] = []
    for path, lo, hi in _raw_citations(rec):
        norm = path.replace("\\", "/")
        if norm in hashed:
            rel = norm
        else:
            name = norm.rsplit("/", 1)[-1]
            hits = sorted(p for p in hashed if p.rsplit("/", 1)[-1] == name)
            if len(hits) == 1:
                rel = hits[0]
            elif len(hits) > 1:
                mine = [p for p in hits if p in own]
                if len(mine) == 1:
                    rel = mine[0]
                else:
                    reasons.append(f"ambiguous citation: {path}")
                    continue
            else:
                reasons.append(f"cites unhashed file: {norm}")
                continue
        if rel.startswith(citation_check._NEVER_HASHED):
            continue
        groups.setdefault(rel, []).append((lo, hi))
    return groups, reasons


def _game_root() -> Path:
    return harness.DEFAULT_GAME_ROOT


def classify_record(rec: dict, historical=None, current=None,
                     game_root: Path | None = None) -> dict:
    """Classify one stale record.

    `historical(key)` -> text or None, keyed by (path, sha256) — defaults to
    `historical_text` (git-backed). `current(path)` -> text or None, keyed by
    a bare repo/game-relative path — defaults to reading disk. Both are
    dependency-injected so this function is testable without git or the real
    tree (see test/test_stale_triage.py).
    """
    historical = historical or (lambda key: historical_text(*key))
    root = game_root or _game_root()

    def default_current(path: str) -> str | None:
        return current_text(path, root) if _looks_game(path, rec) else current_text(path, REPO)

    if current is None:
        current = default_current

    unit = rec.get("unit", "?")
    entries = _all_source_entries(rec)
    cite_groups, cite_reasons = _resolve_citations(rec)

    files_out: list[dict] = []
    class_a = True
    reasons: list[str] = list(cite_reasons)
    if cite_reasons:
        class_a = False

    # 1. every hashed entry: game side just compares current vs recorded;
    #    sim side needs the historical text recovered.
    for path, recorded_sha, side in entries:
        if path.startswith(citation_check._NEVER_HASHED):
            continue
        cur_text = current(path)
        cur_sha = harness_normalized_sha(cur_text) if cur_text is not None else None
        file_rec = {"path": path, "side": side, "recorded_sha": recorded_sha,
                    "current_sha": cur_sha, "historical_found": None, "spans": []}

        if side == "game":
            if cur_sha != recorded_sha:
                class_a = False
                reasons.append("game-source-changed")
            file_rec["historical_found"] = (cur_sha == recorded_sha)
            files_out.append(file_rec)
            continue

        # sim side: recover the historical text the hash was taken over.
        hist_text = historical((path, recorded_sha))
        file_rec["historical_found"] = hist_text is not None
        if hist_text is None:
            class_a = False
            reasons.append(f"historical text not recoverable: {path}")
            files_out.append(file_rec)
            continue

        spans = cite_groups.get(path, [])
        span_rows = []
        all_identical = True
        if cur_text is None:
            all_identical = False
        else:
            for lo, hi in spans:
                ident = span_identical(hist_text, cur_text, lo, hi)
                span_rows.append({"cite": f"{path}:{lo}-{hi}" if hi != lo else f"{path}:{lo}",
                                  "identical": ident})
                if not ident:
                    all_identical = False
        file_rec["spans"] = span_rows
        if not all_identical:
            class_a = False
            reasons.append(f"span changed: {path}")
        files_out.append(file_rec)

    cls = "a" if class_a else "b"
    reason = "; ".join(reasons) if reasons else "all cited spans byte-identical"
    return {"unit": unit, "class": cls, "files": files_out, "reason": reason}


def _looks_game(path: str, rec: dict) -> bool:
    """Best-effort side lookup for a bare `current(path)` default — checks
    the record's own source entries first."""
    for p, _, side in _all_source_entries(rec):
        if p == path:
            return side == "game"
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", help="only this kind (default: all)")
    ap.add_argument("--out", default=str(REPO / "audit" / "stale-sweep" / "receipts.json"))
    args = ap.parse_args(argv)

    records_dir = harness.DEFAULT_AUDITS_DIR
    kinds = [args.kind] if args.kind else sorted(
        p.name for p in records_dir.iterdir() if p.is_dir())

    receipts: list[dict] = []
    per_kind: dict[str, dict[str, int]] = {}

    for kind in kinds:
        kdir = records_dir / kind
        files = sorted(kdir.glob("*.json")) if kdir.is_dir() else []
        print(f"[{kind}] scanning {len(files)} record(s)...")
        a = b = 0
        for rec_path in files:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            unit = rec.get("unit", rec_path.stem)
            if not audit_status._is_stale(rec, unit, harness.DEFAULT_GAME_ROOT):
                continue
            out = classify_record(rec)
            receipts.append(out)
            if out["class"] == "a":
                a += 1
            else:
                b += 1
        per_kind[kind] = {"a": a, "b": b}
        print(f"[{kind}] class-a {a} / class-b {b}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipts, indent=2), encoding="utf-8")

    total_a = sum(v["a"] for v in per_kind.values())
    total_b = sum(v["b"] for v in per_kind.values())
    lines = [f"{kind}: class-a {v['a']} / class-b {v['b']}" for kind, v in per_kind.items()]
    lines.append(f"TOTAL: class-a {total_a} / class-b {total_b} "
                 f"(classified {total_a + total_b})")
    summary = "\n".join(lines)
    print("\n" + summary)
    (out_path.parent / "SUMMARY.txt").write_text(summary + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
