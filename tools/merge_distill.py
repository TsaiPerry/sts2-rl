#!/usr/bin/env python
"""Merge the shard sets of several `tools/search_worker.py` parts into one.

Generation now runs as waves of parallel workers, each writing its own `--out`
directory (`.npz` shards + a `provenance.json`). The trainer wants ONE shard
set, so the parts have to be concatenated — which is three jobs, not one:

* **Copy and rename.** Every worker names its shards `shard_0000.npz` upward,
  so all parts collide. Files land here as `p<N>-<original>.npz`, N being the
  part's index on the command line, which keeps the producer's own ordering
  visible inside each part and makes the merged names unique by construction.
* **Add up the counters.** The merged `stats` is the field-wise sum of the
  parts' numeric leaves, with dict-valued leaves (`room_hist`) summed per key.
  `records` is the sum of the parts' record counts — each one VERIFIED against
  the rows actually present in that part's `.npz` files, because a provenance
  number that disagrees with the arrays means one of the two is describing a
  run that did not happen, and silently trusting either would put a wrong
  denominator under every rate the run is later judged by.
* **Refuse mixed generators.** A shard set is only meaningful against the obs
  contract and the search config it was written under. Parts that disagree on
  `obs_schema`, `card_obs`, `k`, `temperature`, `min_score_gap` or `ckpt` are
  not two halves of one dataset; merging them would produce a directory the
  trainer cannot detect anything wrong with (see
  `train_torch.check_distill_provenance`, which can only compare the ONE stamp
  the merged file ends up carrying). `min_score_gap` matters as much as the
  rest: it decides WHICH decisions became records, so a filtered part and an
  unfiltered one describe different populations, not different halves.

Everything the parts agreed on is carried through by DEEP-COPYING part 0's
provenance, and each part's own `{part, bank, seed, stats}` is deep-copied
into `merged_from`. The deep copies are the point of this module: the ad-hoc
snippets it replaces used shallow copies, so accumulating into the merged
`stats` mutated the per-part records through the shared dict — the aliasing
bug found in the 08-28 v26 diagnosis, where the audit trail quietly became
len(parts) copies of the total.

Usage:

    python tools/merge_distill.py PART_DIR [PART_DIR ...] --out DIR
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np

#: The provenance fields that must be IDENTICAL across parts. Not a style
#: preference: each one changes what the arrays or the targets mean, and none
#: of them is recoverable from the merged directory afterwards.
MUST_MATCH = ("obs_schema", "card_obs", "k", "temperature", "min_score_gap",
              "ckpt")

#: Fields whose ABSENCE means a definite value rather than "unknown".
#: `min_score_gap` (search_worker's decisiveness filter, added 2026-08-28)
#: is the only one: every part written before that flag existed kept EVERY
#: searched decision, which is exactly what `--min-score-gap 0.0` means today.
#: So a missing key compares equal to 0.0 — a pre-filter part still merges
#: with an explicitly unfiltered one, and neither merges with a FILTERED part,
#: whose records are a decisiveness-biased subsample and would silently change
#: what the merged stamp describes.
MUST_MATCH_DEFAULTS = {"min_score_gap": 0.0}

#: The per-part fields kept in `merged_from`. `run_id` is here so each source
#: run stays identifiable after the merge, even though the merged directory as
#: a whole no longer has a single run_id (its shards come from many runs).
PART_FIELDS = ("run_id", "bank", "seed", "stats")

#: The arrays every shard carries. An intentional DUPLICATE of
#: `search_worker.SHARD_KEYS`, kept local so that importing merge_distill never
#: imports search_worker (and through it the sim). test_merge_distill.py
#: asserts the two stay equal.
_SHARD_KEYS = ("f", "i", "mask", "tgt_idx", "tgt_p")


# ════════════════════════════════════════════════════════════════════════════
# Reading a part
# ════════════════════════════════════════════════════════════════════════════


def _read_provenance(part: Path) -> dict:
    prov_path = part / "provenance.json"
    if not prov_path.is_file():
        raise SystemExit(
            f"{part}: no provenance.json — tools/search_worker.py always "
            f"writes one, so this is not a shard-set part directory")
    try:
        # utf-8-sig: a hand-edited file round-tripped through a Windows editor
        # picks up a BOM, and refusing a part over a byte order mark would be
        # a maddening false alarm. Plain UTF-8 decodes unchanged.
        prov = json.loads(prov_path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise SystemExit(f"{prov_path}: not valid JSON ({exc})")
    if not isinstance(prov, dict):
        raise SystemExit(f"{prov_path}: expected a JSON object")
    return prov


def _match_value(prov: dict, key: str):
    """The value of a `MUST_MATCH` field, with `MUST_MATCH_DEFAULTS` applied.

    A key that is present but JSON-null is treated the same as an absent one:
    both say "this generator did not record the field", and for the fields in
    the defaults table that has exactly one meaning.
    """
    val = prov.get(key)
    if key in MUST_MATCH_DEFAULTS:
        return float(MUST_MATCH_DEFAULTS[key] if val is None else val)
    return val


def _shard_rows(path: Path) -> int:
    """The record count of one shard, read off the arrays themselves.

    All five arrays must agree — a shard whose `mask` is shorter than its `f`
    is corrupt, and concatenating it would misalign every record after it.
    """
    with np.load(path) as data:
        missing = [k for k in _SHARD_KEYS if k not in data]
        if missing:
            raise SystemExit(f"{path}: not a distill shard — missing {missing}")
        rows = {k: int(data[k].shape[0]) for k in _SHARD_KEYS}
    if len(set(rows.values())) != 1:
        raise SystemExit(f"{path}: shard arrays disagree on row count {rows}")
    return next(iter(rows.values()))


def _shard_run_id(path: Path):
    """The `run_id` stamped in a shard by search_worker, or None if absent.

    Shards written before the stamp existed (and the current in-flight
    v27_batch1 parts) carry no `run_id`; those fall back to the mtime check.
    """
    with np.load(path) as data:
        if "run_id" not in data:
            return None
        arr = data["run_id"]
        return str(arr.reshape(-1)[0]) if arr.size else None


#: A shard's mtime may exceed its provenance's by at most this, in seconds.
#: A clean part writes every shard THEN the provenance, so the provenance is
#: always the newest file (observed delta 0.0s across all 15 clean v27_batch1
#: parts). A larger positive gap means a shard was written AFTER the run that
#: stamped the provenance "finished" — i.e. a re-run is overwriting the part in
#: place (the 08-30 clobber, +36000..58000s) — so the shards no longer all
#: belong to the run the provenance describes. The tolerance only absorbs
#: filesystem timestamp granularity.
_MTIME_TOL_S = 2.0


def _check_part_consistency(part: Path, prov: dict, shards: "list[Path]") -> None:
    """Refuse a part whose shards do not all belong to ONE run.

    Two independent signals, because the authoritative one (run_id) is absent
    on legacy and in-flight parts:

    * **run_id** (authoritative when present): every shard must carry the same
      run_id as the provenance. A shard from a different run — a hybrid left by
      an interrupted regeneration — is caught even if its mtime was touched.
    * **mtime** (the fallback that covers run_id-less parts): no shard may be
      newer than the provenance (see `_MTIME_TOL_S`). This is what catches the
      current, un-stamped v27_batch1 parts if one is ever merged mid-clobber.

    Neither is a heuristic that a clean part can trip: a clean part has one
    run_id everywhere and a provenance newer than every shard.
    """
    prov_id = prov.get("run_id")
    if prov_id is not None:
        for sh in shards:
            sid = _shard_run_id(sh)
            if sid is None:
                raise SystemExit(
                    f"{part}: provenance.json has run_id {prov_id!r} but shard "
                    f"{sh.name} carries none — it was not written by that run. "
                    f"This directory mixes shards from different runs; refusing "
                    f"to merge a part whose shards do not all belong together.")
            if sid != prov_id:
                raise SystemExit(
                    f"{part}: shard {sh.name} has run_id {sid!r} but "
                    f"provenance.json has {prov_id!r}. The directory holds "
                    f"shards from two different runs under one provenance (an "
                    f"interrupted regeneration); refusing to merge a hybrid.")

    prov_mtime = (part / "provenance.json").stat().st_mtime
    late = [(sh.name, sh.stat().st_mtime - prov_mtime) for sh in shards
            if sh.stat().st_mtime - prov_mtime > _MTIME_TOL_S]
    if late:
        worst = max(late, key=lambda t: t[1])
        raise SystemExit(
            f"{part}: shard {worst[0]} is {worst[1]:.0f}s NEWER than "
            f"provenance.json, which a completed run writes last. A shard "
            f"written after the run finished means the part is being "
            f"overwritten in place (a re-run is clobbering it) — its shards no "
            f"longer all belong to the run the provenance describes. Refusing "
            f"to merge a directory mid-regeneration; let it finish or "
            f"regenerate it into a fresh dir. ({len(late)} shard(s) affected.)")


def _part_shards(part: Path, prov: dict) -> "list[Path]":
    """The part's shard files, in the order its provenance lists them.

    The provenance list is authoritative because records are ordered WITHIN a
    shard and the producer wrote that order down; a directory listing is only
    the fallback for a hand-built part with no `shards` key.
    """
    names = prov.get("shards")
    if names is None:
        return sorted(p for p in part.iterdir() if p.suffix == ".npz")
    if not isinstance(names, list):
        raise SystemExit(f"{part}/provenance.json: 'shards' is not a list")
    paths = []
    for name in names:
        p = part / str(name)
        if not p.is_file():
            raise SystemExit(
                f"{part}: provenance.json lists shard {name!r} but that file "
                f"is not there")
        paths.append(p)
    stray = sorted(p.name for p in part.iterdir()
                   if p.suffix == ".npz" and p.name not in set(map(str, names)))
    if stray:
        raise SystemExit(
            f"{part}: .npz files not listed in provenance.json: {stray} — "
            f"merging would either drop them or count them twice")
    return paths


# ════════════════════════════════════════════════════════════════════════════
# Summing
# ════════════════════════════════════════════════════════════════════════════


def _is_number(v) -> bool:
    # bool is an int subclass, but "sum the flags" is meaningless; a bool leaf
    # is a description, so it is carried, not added.
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sum_stats(parts_stats: "list[dict]") -> dict:
    """Field-wise sum of the parts' stats dicts.

    Numeric leaves add. Dict-valued leaves (`room_hist`) are merged by summing
    per key over the union of keys. Anything else (a string, a bool) is a
    description rather than a counter and keeps the first part's value.
    """
    out: dict = {}
    for stats in parts_stats:
        if not isinstance(stats, dict):
            raise SystemExit(f"a part's 'stats' is not an object: {stats!r}")
        for key, val in stats.items():
            if key not in out:
                out[key] = copy.deepcopy(val)
                continue
            cur = out[key]
            if _is_number(cur) and _is_number(val):
                out[key] = cur + val
            elif isinstance(cur, dict) and isinstance(val, dict):
                for sub, sval in val.items():
                    if sub in cur and _is_number(cur[sub]) and _is_number(sval):
                        cur[sub] = cur[sub] + sval
                    elif sub not in cur:
                        cur[sub] = copy.deepcopy(sval)
            # else: keep the first part's value.
    # Floats accumulated from rounded per-part seconds pick up binary noise
    # (1.5 + 1.2 + 0.3 = 2.9999999999999996); the producer rounds to 3, so so
    # does the sum.
    for key, val in out.items():
        if isinstance(val, float):
            out[key] = round(val, 3)
    return out


# ════════════════════════════════════════════════════════════════════════════
# The merge
# ════════════════════════════════════════════════════════════════════════════


def merge_distill(part_dirs: "list[str]", out_dir: str) -> dict:
    """Merge `part_dirs` into `out_dir`; return the merged provenance dict.

    The merged provenance is written to `out_dir/provenance.json` as well as
    returned. Nothing is written until every part has been validated, so a
    refused merge leaves no half-built directory behind.
    """
    if not part_dirs:
        raise SystemExit("merge_distill: no part directories given")

    parts = [Path(p) for p in part_dirs]
    for part in parts:
        if not part.is_dir():
            raise SystemExit(f"{part}: not a directory")

    # ── validate every part BEFORE copying a single byte ───────────────────
    provs, shard_lists, counts = [], [], []
    for idx, part in enumerate(parts):
        prov = _read_provenance(part)
        if idx:
            for key in MUST_MATCH:
                first = _match_value(provs[0], key)
                got = _match_value(prov, key)
                if first != got:
                    raise SystemExit(
                        f"{part}: {key}={got!r} but {parts[0]} has "
                        f"{key}={first!r}. These parts were written by "
                        f"different generators; merging them would produce a "
                        f"shard set whose single provenance stamp lies about "
                        f"half its records.")
        shards = _part_shards(part, prov)
        if not shards:
            raise SystemExit(f"{part}: no .npz shards found there")
        _check_part_consistency(part, prov, shards)
        actual = sum(_shard_rows(p) for p in shards)
        claimed = prov.get("records")
        if claimed is not None and int(claimed) != actual:
            raise SystemExit(
                f"{part}: provenance.json says records={claimed} but its "
                f"shards hold {actual} rows. One of the two describes a run "
                f"that did not happen; refusing to merge a part whose own "
                f"record count cannot be trusted.")
        provs.append(prov)
        shard_lists.append(shards)
        counts.append(actual)

    # ── copy ───────────────────────────────────────────────────────────────
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    existing = sorted(p.name for p in out.iterdir() if p.suffix == ".npz")
    if existing:
        raise SystemExit(
            f"{out}: already holds {len(existing)} .npz file(s) "
            f"({existing[0]} ...) — merging into it would mix shard sets; "
            f"remove it or pick a fresh --out")

    merged_names: "list[str]" = []
    for idx, shards in enumerate(shard_lists):
        for src in shards:
            name = f"p{idx}-{src.name}"
            shutil.copy2(src, out / name)
            merged_names.append(name)
    assert len(set(merged_names)) == len(merged_names)   # by construction

    # ── provenance ─────────────────────────────────────────────────────────
    merged = copy.deepcopy(provs[0])
    # Write the defaulted fields back explicitly, so a merge of pre-4b parts
    # produces a directory that STATES it is unfiltered rather than one that
    # is merely silent about it — the next merge that includes it then reads
    # the key instead of re-deriving the default.
    for key in MUST_MATCH_DEFAULTS:
        merged[key] = _match_value(provs[0], key)
    # The merged directory legitimately holds shards from every part, so it has
    # no single run_id; carrying part 0's forward would make a re-merge of this
    # directory refuse itself (its shards' ids would disagree with the stamp).
    # Each source id is preserved per-part in merged_from instead.
    merged["run_id"] = None
    merged["shards"] = merged_names
    merged["records"] = sum(counts)
    merged["stats"] = _sum_stats([p.get("stats", {}) for p in provs])
    banks, seen = [], set()
    for prov in provs:
        b = str(prov.get("bank"))
        if b not in seen:
            seen.add(b)
            banks.append(b)
    merged["bank"] = " + ".join(banks)
    merged["merged_from"] = [
        {"part": str(part), "records": count,
         **{f: copy.deepcopy(prov.get(f)) for f in PART_FIELDS}}
        for part, prov, count in zip(parts, provs, counts)]

    (out / "provenance.json").write_text(json.dumps(merged, indent=2),
                                         encoding="utf-8")
    return merged


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Merge search_worker part dirs into one shard set.")
    ap.add_argument("part_dirs", nargs="+", metavar="PART_DIR",
                    help="worker --out directories, in the order to merge")
    ap.add_argument("--out", required=True, metavar="DIR",
                    help="destination shard-set directory (must hold no .npz)")
    args = ap.parse_args(argv)

    prov = merge_distill(args.part_dirs, args.out)
    print(f"merged {len(args.part_dirs)} part(s) -> {args.out}")
    print(f"  {prov['records']} records in {len(prov['shards'])} shard(s)")
    for entry in prov["merged_from"]:
        print(f"  part {entry['part']}: {entry['records']} records "
              f"(seed {entry['seed']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
