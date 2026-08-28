"""Split a snapshot bank JSONL into N disjoint banks, round-robin.

`search_worker.py` has no `--shard` flag and its fight list always starts at
fight 0 (`snap_idx = fight % len(snaps)`), so N parallel workers pointed at
the SAME bank all walk the same leading snapshots — N stochastic replays of a
narrow slice instead of N times the coverage. `--seed` does not help: it
feeds the reset seed, not the snapshot index.

Splitting round-robin (line i -> part i % n) gives each worker its own pool
while preserving the act/room mix, since the harvest writes snapshots in
episode order. Each part keeps the bank's `snapshot_schema` header line.

    py tools/split_bank.py runs/snapshots/v24s27_bank_asc10.jsonl 6
      -> runs/snapshots/v24s27_bank_asc10.p0.jsonl ... .p5.jsonl
"""
from __future__ import annotations

import argparse
import os


def split_bank(path: str, n: int) -> "list[str]":
    stem, ext = os.path.splitext(path)
    outs = [f"{stem}.p{i}{ext}" for i in range(n)]
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
        if "snapshot_schema" not in header:
            raise SystemExit(f"{path}: first line is not a snapshot_schema header")
        handles = [open(o, "w", encoding="utf-8") for o in outs]
        try:
            for h in handles:
                h.write(header if header.endswith("\n") else header + "\n")
            counts = [0] * n
            for i, line in enumerate(ln for ln in f if ln.strip()):
                h = handles[i % n]
                h.write(line if line.endswith("\n") else line + "\n")
                counts[i % n] += 1
        finally:
            for h in handles:
                h.close()
    for o, c in zip(outs, counts):
        print(f"{o}  {c} snapshots")
    return outs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bank")
    ap.add_argument("parts", type=int)
    args = ap.parse_args()
    if args.parts < 2:
        raise SystemExit("parts must be >= 2")
    split_bank(args.bank, args.parts)


if __name__ == "__main__":
    main()
