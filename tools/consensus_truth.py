"""Noise-robust truth for the value-fit gate: R independent gold search runs
vote on each decision's winner; a decision is STABLE-DECISIVE when a strict
majority agree AND the median cross-run raw gap exceeds tau. Any estimator
(e.g. the new critic's steps=0 run) is graded by how often its winner matches
that consensus on the stable-decisive subset (spec 2026-08-31, gate = 0.80)."""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.mcheck_analyze import load_records, winner_and_gap


def _winners_gaps(path, temperature):
    f, i, _m, tidx, tp = load_records(path)
    n = len(tidx)
    w = np.empty(n, np.int64); g = np.empty(n)
    for r in range(n):
        w[r], g[r], _ = winner_and_gap(tidx[r], tp[r], temperature)
    return f, w, g


def build_consensus(gold_dirs, temperature=0.25):
    runs = [_winners_gaps(d, temperature) for d in gold_dirs]
    n = min(len(w) for _f, w, _g in runs)
    f0 = runs[0][0][:n]
    for f, _w, _g in runs[1:]:
        if not np.array_equal(f[:n], f0):
            raise ValueError("consensus: gold dirs are not record-aligned (f differs)")
    R = len(runs)
    winner = np.full(n, -1, np.int64); stable = np.zeros(n, bool); mgap = np.zeros(n)
    for r in range(n):
        votes = Counter(int(runs[k][1][r]) for k in range(R))
        top, cnt = votes.most_common(1)[0]
        winner[r] = top
        stable[r] = cnt * 2 > R                       # strict majority
        mgap[r] = float(np.median([runs[k][2][r] for k in range(R)]))
    return {"winner": winner, "stable": stable, "median_gap": mgap, "n": n, "R": R, "f": f0}


def grade(estimator_dir, gold_dirs, tau=0.3, temperature=0.25):
    cons = build_consensus(gold_dirs, temperature)
    ef, ew, _eg = _winners_gaps(estimator_dir, temperature)
    n = min(cons["n"], len(ew))
    if not np.array_equal(ef[:n], cons["f"][:n]):
        raise ValueError(
            "grade: estimator dir is not record-aligned with the gold consensus "
            "(f differs) -- the steps=0 run must use the SAME bank/--decisions/--seed "
            "as the gold runs")
    sel = cons["stable"][:n] & (cons["median_gap"][:n] > tau)
    k = int(sel.sum())
    agree = int((ew[:n][sel] == cons["winner"][:n][sel]).sum())
    return {"n_stable_decisive": k, "agree": agree,
            "rate": (agree / k if k else float("nan")), "tau": tau}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", action="append", required=True, metavar="DIR")
    ap.add_argument("--est", required=True, metavar="DIR")
    ap.add_argument("--tau", type=float, default=0.3)
    ap.add_argument("--temperature", type=float, default=0.25)
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args(argv)
    res = grade(a.est, a.gold, tau=a.tau, temperature=a.temperature)
    cons = build_consensus(a.gold, a.temperature)
    res["n_stable_total"] = int(cons["stable"].sum())
    print(json.dumps(res, indent=2))
    print(f"GATE: steps=0 agreement {res['rate']:.3f} on {res['n_stable_decisive']} "
          f"stable-decisive decisions (pass >= 0.80)")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
