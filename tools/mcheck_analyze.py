"""mcheck_analyze.py — how reliable is the m=8 search winner?

The v27 batch-1 targets come from a one-ply expectimax whose candidate scores
are the mean of only ``--m 8`` rollouts, then filtered to decisions whose raw
top1-top2 score gap exceeds 0.05 (``--min-score-gap``). This tool asks whether
that 8-rollout winner is a stable signal or a coin flip dressed up by the
filter's winner's-curse (conditioning on gap>0.05 preferentially admits the
decision where the winner got a lucky-high draw).

Method: two ``search_worker`` runs over the SAME bank / seed / candidates,
differing ONLY in ``--m`` (8 vs a larger reference, e.g. 32), both written
UNFILTERED (``--min-score-gap 0``) so the collection walk — which is a pure
function of ``(seed, fight, d)`` and never touches ``m`` — scores the identical
set of decisions in the identical order. Record ``n`` in one run is the same
game state as record ``n`` in the other (asserted on ``f``/``i``). Only
``tgt_p`` moves with ``m``.

For each decision we recover, from the stored temperature-``T`` targets alone:
  * the winner = the action id at ``argmax(tgt_p)`` (softmax is monotone in the
    raw score, so its argmax IS the raw-score argmax);
  * the raw score gap  δ = T * log(p1 / p2)  over the top two valid ``tgt_p``
    (exact: p_i ∝ exp(s_i / T)  ⟹  log(p1/p2) = (s1 - s2)/T).

Headline: on the subset the m=8 filter KEEPS (δ_m8 > --min-score-gap), how
often does the m=REF winner agree? High agreement ⟹ the 8-rollout target is
reliable and cycle 1 is safe to launch; low agreement ⟹ the filter is largely
selecting noise and the fix is more rollouts, not more training.

Usage:
    tools/mcheck_analyze.py runs/distill/v27_mcheck/m8 runs/distill/v27_mcheck/m32 \\
        [--temperature 0.25] [--min-score-gap 0.05] [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from tools.search_worker import iter_shards, PAD


def load_records(path):
    """Concatenate a shard set into aligned (f, i, mask, tgt_idx, tgt_p) arrays,
    in shard-then-within-shard order — the same order the writer used."""
    fs, iis, masks, tidx, tp = [], [], [], [], []
    for sh in iter_shards(path):
        fs.append(sh["f"]); iis.append(sh["i"]); masks.append(sh["mask"])
        tidx.append(sh["tgt_idx"]); tp.append(sh["tgt_p"])
    if not fs:
        raise SystemExit(f"{path}: no shards")
    return (np.concatenate(fs), np.concatenate(iis), np.concatenate(masks),
            np.concatenate(tidx), np.concatenate(tp))


def winner_and_gap(tgt_idx_row, tgt_p_row, temperature):
    """(winning action id, δ, n_valid) for one record from its targets alone.

    δ = T*log(p1/p2) over the top two VALID probabilities; +inf for a lone
    candidate (nothing to be tied with — the score_gap convention)."""
    valid = tgt_idx_row >= 0
    ids = tgt_idx_row[valid].astype(np.int64)
    p = tgt_p_row[valid].astype(np.float64)
    if p.size == 0:
        return -1, 0.0, 0
    order = np.argsort(-p)                      # descending prob
    win_id = int(ids[order[0]])
    if p.size == 1:
        return win_id, float("inf"), 1
    p1, p2 = float(p[order[0]]), float(p[order[1]])
    # p2 can underflow float16 to 0 for a very sharp target; guard it.
    gap = float("inf") if p2 <= 0.0 else float(temperature * np.log(p1 / p2))
    return win_id, gap, int(p.size)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("m8_dir", help="the m=8 shard set (the batch's actual m)")
    ap.add_argument("ref_dir", help="the reference shard set (larger m)")
    ap.add_argument("--temperature", type=float, default=0.25,
                    help="the T both sets were written at (default 0.25)")
    ap.add_argument("--min-score-gap", type=float, default=0.05,
                    help="the batch's decisiveness filter (default 0.05)")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    f8, i8, m8mask, tidx8, tp8 = load_records(args.m8_dir)
    fR, iR, mRmask, tidxR, tpR = load_records(args.ref_dir)

    n = min(len(f8), len(fR))
    if len(f8) != len(fR):
        print(f"WARNING: record counts differ (m8={len(f8)}, ref={len(fR)}); "
              f"comparing the first {n} (a determinism break would cause this)")
    f8, i8, tidx8, tp8 = f8[:n], i8[:n], tidx8[:n], tp8[:n]
    fR, iR, tidxR, tpR = fR[:n], iR[:n], tidxR[:n], tpR[:n]

    # ── alignment proof: same decisions in the same order ────────────────────
    f_aligned = bool(np.array_equal(f8, fR))
    i_aligned = bool(np.array_equal(i8, iR))
    idx_aligned = bool(np.array_equal(tidx8, tidxR))
    print(f"alignment: f {'OK' if f_aligned else 'MISMATCH'}  "
          f"i {'OK' if i_aligned else 'MISMATCH'}  "
          f"candidate-set {'identical' if idx_aligned else 'differs (compared by action id)'}")
    if not (f_aligned and i_aligned):
        print("  !! obs blocks differ — the two runs did NOT score the same "
              "decisions; results below are not a valid paired comparison.")

    w8 = np.empty(n, dtype=np.int64);  g8 = np.empty(n)
    wR = np.empty(n, dtype=np.int64);  gR = np.empty(n)
    nv8 = np.empty(n, dtype=np.int64)
    for r in range(n):
        w8[r], g8[r], nv8[r] = winner_and_gap(tidx8[r], tp8[r], args.temperature)
        wR[r], gR[r], _ = winner_and_gap(tidxR[r], tpR[r], args.temperature)

    G = args.min_score_gap
    agree = (w8 == wR)
    kept = g8 > G                               # what the m=8 filter would keep

    def rate(sel):
        k = int(sel.sum())
        a = int((agree & sel).sum())
        return a, k, (a / k if k else float("nan"))

    a_all, k_all, r_all = rate(np.ones(n, dtype=bool))
    a_kept, k_kept, r_kept = rate(kept)

    # ── headline ─────────────────────────────────────────────────────────────
    print()
    print("=" * 68)
    print(f"records compared           {n}")
    print(f"m=8 winner == m=REF winner (all decisions)   "
          f"{a_all}/{k_all} = {r_all:.3f}")
    print(f"                           (m=8 KEPT, δ>{G})  "
          f"{a_kept}/{k_kept} = {r_kept:.3f}   <-- the batch's actual targets")
    # how many m8-kept decisions the reference ALSO calls decisive
    refkept = (gR > G) & kept
    print(f"of those {k_kept} m=8-kept, m=REF also δ>{G}:  "
          f"{int(refkept.sum())} ({100*refkept.mean() if n else 0:.0f}% of kept)"
          if k_kept else "")

    # ── agreement by decisiveness band (does confidence track correctness?) ──
    print()
    print("agreement on m=8-kept, by m=8 δ band:")
    bands = [(G, 0.1), (0.1, 0.3), (0.3, 1.0), (1.0, float("inf"))]
    band_out = []
    for lo, hi in bands:
        sel = kept & (g8 > lo) & (g8 <= hi)
        a, k, rr = rate(sel)
        lbl = f"({lo:g}, {hi:g}]" if hi != float("inf") else f"(> {lo:g})"
        print(f"  δ {lbl:<14} {a:>4}/{k:<4} = {rr:.3f}" if k else
              f"  δ {lbl:<14}    (empty)")
        band_out.append({"lo": lo, "hi": hi, "agree": a, "n": k})

    result = {
        "m8_dir": args.m8_dir, "ref_dir": args.ref_dir,
        "temperature": args.temperature, "min_score_gap": G,
        "n_compared": n,
        "f_aligned": f_aligned, "i_aligned": i_aligned,
        "candidate_set_identical": idx_aligned,
        "agree_all": {"agree": a_all, "n": k_all, "rate": r_all},
        "agree_kept": {"agree": a_kept, "n": k_kept, "rate": r_kept},
        "ref_also_kept_of_m8_kept": int(refkept.sum()),
        "bands": band_out,
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2),
                                       encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
