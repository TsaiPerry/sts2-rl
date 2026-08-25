"""One-shot sweep of iter-stamped snapshots left behind by runs that finished
*before* train_torch grew its finish-time cleanup (--cleanup-snapshots).

train_torch now deletes a run's ``<stem>.iterNNNNNN.pt`` snapshots when the run
completes cleanly, but only for runs that finish after that change. This tool
applies the same rule retroactively to what is already on disk.

Same narrow scope as the in-trainer cleanup, for the same reason: the final
``<stem>.pt`` and ``<stem>.best.pt`` are never touched, because the curriculum
scripts chain stages through ``--resume runs/..._sNN.pt``.

Two guards decide whether a run counts as finished, and both must pass:

  * ``<stem>.pt`` exists. train_torch writes it as the last act of a completed
    run; a run killed with Ctrl-C before its first --save-every boundary never
    produces one. This is what protects an interrupted run's snapshots -- the
    whole point of keeping them.
  * nothing under that stem has been modified in the last --min-age-hours.
    A run that is training *right now* also has a <stem>.pt on disk (the live
    checkpoint), so file age is what separates "finished" from "in flight".

Dry run by default. Nothing is deleted without --apply.

    py tools/sweep_snapshots.py                 # report only
    py tools/sweep_snapshots.py --apply         # delete
    py tools/sweep_snapshots.py --apply --stem sts2_run_torch_v8
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import train_torch


@dataclass
class RunFiles:
    stem: str                 # "runs/sts2_run_torch_v8_s0" -- no .pt
    snapshots: list[str]
    final: str | None         # <stem>.pt, if the run ever wrote one
    newest_mtime: float

    @property
    def nbytes(self) -> int:
        return sum(os.path.getsize(p) for p in self.snapshots)

    def verdict(self, now: float, min_age_s: float) -> str | None:
        """None = sweep it; a string = why it was left alone."""
        if self.final is None:
            return "no final .pt (run never finished)"
        age = now - self.newest_mtime
        if age < min_age_s:
            return f"modified {age / 3600:.1f}h ago (may be training now)"
        return None


def collect_runs(runs_dir: str) -> list[RunFiles]:
    """Group every iter snapshot under ``runs_dir`` by the run stem it hangs off."""
    by_stem: dict[str, list[str]] = {}
    for path in glob.glob(os.path.join(runs_dir, "*.iter*.pt")):
        stem = path[:path.rindex(".iter")]
        by_stem.setdefault(stem, []).append(path)

    runs = []
    for stem, snaps in sorted(by_stem.items()):
        final = f"{stem}.pt"
        tracked = snaps + [p for p in (final, train_torch.best_path(final))
                           if os.path.exists(p)]
        runs.append(RunFiles(
            stem=stem,
            snapshots=sorted(snaps),
            final=final if os.path.exists(final) else None,
            newest_mtime=max(os.path.getmtime(p) for p in tracked),
        ))
    return runs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: report what would go)")
    ap.add_argument("--stem", default=None,
                    help="only consider runs whose name contains this substring")
    ap.add_argument("--min-age-hours", type=float, default=6.0,
                    help="leave alone any run touched more recently than this, "
                         "so a live run is never swept (default: 6)")
    args = ap.parse_args()

    runs = collect_runs(args.runs_dir)
    if args.stem:
        runs = [r for r in runs if args.stem in os.path.basename(r.stem)]
    if not runs:
        print(f"No iter snapshots found under {args.runs_dir}/")
        return

    now, min_age_s = time.time(), args.min_age_hours * 3600
    sweep, skip = [], []
    for run in runs:
        (skip if run.verdict(now, min_age_s) else sweep).append(run)

    for run in skip:
        print(f"  SKIP  {os.path.basename(run.stem):<34} "
              f"{len(run.snapshots):>3} snaps  -- {run.verdict(now, min_age_s)}")
    for run in sweep:
        print(f"{'DELETE' if args.apply else '  WOULD':>6}  "
              f"{os.path.basename(run.stem):<34} "
              f"{len(run.snapshots):>3} snaps  {run.nbytes / 1e9:>5.2f} GB")

    total = sum(r.nbytes for r in sweep)
    n_snaps = sum(len(r.snapshots) for r in sweep)
    print(f"\n{len(sweep)} finished run(s), {n_snaps} snapshots, "
          f"{total / 1e9:.2f} GB  ({len(skip)} run(s) left alone)")

    if not args.apply:
        print("Dry run -- nothing deleted. Re-run with --apply.")
        return

    for run in sweep:
        train_torch.cleanup_snapshots(run.final)
    print(f"Deleted {n_snaps} snapshots, reclaimed {total / 1e9:.2f} GB. "
          f"Final .pt and .best.pt for every run kept.")


if __name__ == "__main__":
    main()
