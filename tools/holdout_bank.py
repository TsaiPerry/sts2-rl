"""holdout_bank.py - build a held-out snapshot bank from the UNCONSUMED tails
of distill-batch part-banks (spec 2026-08-28-v26-distill-diagnosis).

search_worker consumes a bank's snapshots sequentially from line 0
(`snap_idx = fight % len(snaps)`), so worker N of batch 1 touched exactly the
first `fights_N` snapshots of its part-bank (85/75/84/72/77/80 per
runs/distill/v26_batch1/provenance.json's merged_from stats). Skipping a
common prefix >= max(fights_N) from EVERY part therefore yields snapshots no
batch-1 worker ever replayed. The pooled survivors are re-split round-robin
(same convention as split_bank.py) so 2 holdout workers get disjoint pools.

    py tools/holdout_bank.py runs/snapshots/v24s27_bank_asc10.p0.jsonl ... \\
        --skip 90 --out-stem runs/snapshots/v24s27_bank_asc10.holdout
      -> ....holdout.p0.jsonl, ....holdout.p1.jsonl
"""
from __future__ import annotations

import argparse


def holdout_bank(banks: "list[str]", skip: int, parts: int,
                 out_stem: str) -> "list[str]":
    header = None
    pooled: "list[str]" = []
    for path in banks:
        with open(path, encoding="utf-8-sig") as fh:
            hdr = fh.readline()
            if "snapshot_schema" not in hdr:
                raise SystemExit(
                    f"{path}: first line is not a snapshot_schema header")
            if not hdr.endswith("\n"):
                hdr += "\n"
            if header is None:
                header = hdr
            elif hdr != header:
                raise SystemExit(
                    f"{path}: snapshot_schema header differs from "
                    f"{banks[0]}'s; refusing to pool mismatched banks")
            snaps = [ln if ln.endswith("\n") else ln + "\n"
                     for ln in fh if ln.strip()]
        if len(snaps) <= skip:
            raise SystemExit(
                f"{path}: only {len(snaps)} snapshots but --skip is {skip}; "
                f"the whole bank would be dropped - wrong bank or wrong skip")
        pooled.extend(snaps[skip:])
    if header is None:
        raise SystemExit("no input banks given")

    outs = [f"{out_stem}.p{i}.jsonl" for i in range(parts)]
    handles = [open(o, "w", encoding="utf-8") for o in outs]
    try:
        for h in handles:
            h.write(header)
        counts = [0] * parts
        for i, line in enumerate(pooled):
            handles[i % parts].write(line)
            counts[i % parts] += 1
    finally:
        for h in handles:
            h.close()
    for o, c in zip(outs, counts):
        print(f"{o}  {c} snapshots")
    return outs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("banks", nargs="+")
    ap.add_argument("--skip", type=int, required=True,
                    help="snapshots to drop from the FRONT of every input "
                         "bank (>= the max consumed prefix)")
    ap.add_argument("--parts", type=int, default=2)
    ap.add_argument("--out-stem", required=True)
    args = ap.parse_args()
    if args.parts < 1:
        raise SystemExit("parts must be >= 1")
    if args.skip < 0:
        raise SystemExit("skip must be >= 0")
    holdout_bank(args.banks, args.skip, args.parts, args.out_stem)


if __name__ == "__main__":
    main()
