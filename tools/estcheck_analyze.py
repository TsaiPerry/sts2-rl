"""estcheck_analyze.py — which cheap estimator best matches a high-m gold?

Follow-up to the m=8 reliability probe (mcheck), which showed the batch-1
targets (m=8, 120-step rollouts) agree with a 4x-lower-variance estimate only
~53% of the time on the kept subset. That probe left one question open: is the
fix "more rollouts" (raise m) or "less variance per rollout" (bootstrap the
critic instead of playing out 120 stochastic steps — the AlphaZero move,
reachable here as `search_worker --rollout-steps 0`, i.e. score = reward +
gamma*V(s'))?

This tool answers it. All estimators are run UNFILTERED over the SAME
bank/seed, so the m- and steps-independent collection walk scores the identical
decisions in identical order (record-aligned; asserted on f/i). One estimator
is the GOLD standard (large m, full-length rollouts — our best available
"truth"). For every other estimator we ask: on the decisions the gold calls
genuinely DECISIVE (gold raw gap > threshold, so a real best move exists), does
the estimator pick the gold's winner?

  high agreement for `steps=0` (1-ply critic)  -> a near-free low-variance
      expert exists; rebuild target construction around it, small clean batch.
  no estimator matches the gold, AND gold is unstable vs a second large-m run
      -> the decisions are true ties / the critic is too weak; the distillation
      lever is exhausted (pivot to the reward-ablation fork).

Usage:
    tools/estcheck_analyze.py GOLD_DIR --est NAME=DIR [--est NAME=DIR ...] \\
        [--temperature 0.25] [--thresholds 0.1,0.3,0.5] [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from tools.mcheck_analyze import load_records, winner_and_gap


def winners_gaps(path, temperature):
    _f, _i, _m, tidx, tp = load_records(path)
    n = len(tidx)
    w = np.empty(n, dtype=np.int64); g = np.empty(n)
    for r in range(n):
        w[r], g[r], _ = winner_and_gap(tidx[r], tp[r], temperature)
    return (_f, _i, w, g)


def provenance_cost(path):
    p = json.loads((Path(path) / "provenance.json").read_text())
    s = p.get("stats", {})
    return {"m": p.get("m"), "rollout_steps": p.get("rollout_steps"),
            "records": p.get("records"),
            "search_seconds": s.get("search_seconds"),
            "sec_per_dec": (s.get("search_seconds") / p["records"]
                            if p.get("records") else None)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gold_dir")
    ap.add_argument("--est", action="append", default=[], metavar="NAME=DIR",
                    help="an estimator to grade against the gold (repeatable)")
    ap.add_argument("--temperature", type=float, default=0.25)
    ap.add_argument("--thresholds", default="0.1,0.3,0.5",
                    help="gold raw-gap cutoffs defining 'decisive' (comma list)")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    ests = []
    for spec in args.est:
        if "=" not in spec:
            ap.error(f"--est must be NAME=DIR, got {spec!r}")
        name, d = spec.split("=", 1)
        ests.append((name, d))

    gf, gi, gw, gg = winners_gaps(args.gold_dir, args.temperature)
    ng = len(gw)
    gcost = provenance_cost(args.gold_dir)
    print(f"GOLD {args.gold_dir}  m={gcost['m']} steps={gcost['rollout_steps']}  "
          f"{ng} decisions  {gcost['sec_per_dec']:.1f}s/dec"
          if gcost['sec_per_dec'] else f"GOLD {args.gold_dir}  {ng} decisions")

    # gold's own decisiveness profile
    finite = gg[np.isfinite(gg)]
    print(f"gold raw-gap: median {np.median(finite):.3f}  "
          f"|  decisive counts: " +
          "  ".join(f">{t}:{int((gg>t).sum())}" for t in thresholds))
    print()

    rows = []
    header = f"{'estimator':<14}{'m':>4}{'stp':>5}{'s/dec':>8}   " + \
             "  ".join(f'gold>{t}' for t in thresholds)
    print(header)
    print("-" * len(header))
    for name, d in ests:
        ef, ei, ew, eg = winners_gaps(d, args.temperature)
        n = min(ng, len(ew))
        aligned = bool(np.array_equal(gf[:n], ef[:n]) and np.array_equal(gi[:n], ei[:n]))
        cost = provenance_cost(d)
        cells = []
        rec = {"name": name, "dir": d, "aligned": aligned,
               "m": cost["m"], "rollout_steps": cost["rollout_steps"],
               "sec_per_dec": cost["sec_per_dec"], "by_threshold": {}}
        for t in thresholds:
            sel = (gg[:n] > t)
            k = int(sel.sum())
            a = int(((gw[:n] == ew[:n]) & sel).sum())
            cells.append(f"{a:>2}/{k:<2}={a/k:.2f}" if k else "  -   ")
            rec["by_threshold"][str(t)] = {"agree": a, "n": k}
        spd = f"{cost['sec_per_dec']:.1f}" if cost['sec_per_dec'] else "?"
        flag = "" if aligned else "  !! NOT ALIGNED"
        print(f"{name:<14}{str(cost['m']):>4}{str(cost['rollout_steps']):>5}"
              f"{spd:>8}   " + "  ".join(cells) + flag)
        rows.append(rec)

    print()
    print("read: 'gold>t' = winner-agreement WITH gold on decisions whose gold "
          "raw gap exceeds t (a real best move exists). High for steps=0 means "
          "the 1-ply critic is a reliable, near-free expert on decisive calls.")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "gold_dir": args.gold_dir, "gold": gcost,
            "temperature": args.temperature, "thresholds": thresholds,
            "n_gold": ng, "estimators": rows}, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
