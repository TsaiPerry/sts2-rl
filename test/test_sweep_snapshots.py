"""Tests for tools/sweep_snapshots.py -- the retroactive sweep of snapshots
left by runs that finished before train_torch grew its finish-time cleanup.

This tool deletes files, so the two guards that decide *which* runs it touches
are what these cover: an unfinished run (no final .pt) and a possibly-live run
(recently modified) must both survive.
"""
from __future__ import annotations

import os
import time

import pytest

from tools import sweep_snapshots

DAY = 24 * 3600
MIN_AGE = 6 * 3600


def lay_down(tmp_path, name, *, snaps=(10, 20, 30), final=True, best=True,
             age_s=DAY):
    """Write one run's files and backdate them all by ``age_s``."""
    paths = [tmp_path / f"{name}.iter{i:06d}.pt" for i in snaps]
    if final:
        paths.append(tmp_path / f"{name}.pt")
    if best:
        paths.append(tmp_path / f"{name}.best.pt")
    when = time.time() - age_s
    for p in paths:
        p.write_bytes(b"x" * 1024)
        os.utime(p, (when, when))
    return paths


def verdicts(tmp_path, min_age_s=MIN_AGE):
    now = time.time()
    return {os.path.basename(r.stem): r.verdict(now, min_age_s)
            for r in sweep_snapshots.collect_runs(str(tmp_path))}


def test_finished_run_is_swept(tmp_path):
    lay_down(tmp_path, "run_a")
    assert verdicts(tmp_path)["run_a"] is None


def test_run_without_a_final_checkpoint_is_left_alone(tmp_path):
    """The interrupted-run case -- exactly what the snapshots are there for."""
    lay_down(tmp_path, "smoke", final=False)
    assert "no final .pt" in verdicts(tmp_path)["smoke"]


def test_recently_touched_run_is_left_alone(tmp_path):
    """A live run also has a <stem>.pt on disk; age is what separates them."""
    lay_down(tmp_path, "live", age_s=60)
    assert "may be training now" in verdicts(tmp_path)["live"]


def test_a_live_runs_recent_final_pt_protects_older_snapshots(tmp_path):
    """Snapshots can be hours old while the run is still going -- the guard
    reads the newest of ALL the run's files, not just the snapshots."""
    lay_down(tmp_path, "live", age_s=DAY)
    final = tmp_path / "live.pt"
    os.utime(final, None)                       # trainer just wrote it
    assert "may be training now" in verdicts(tmp_path)["live"]


def test_runs_are_grouped_by_stem_not_conflated(tmp_path):
    lay_down(tmp_path, "run_a", snaps=(10, 20))
    lay_down(tmp_path, "run_b", snaps=(10, 20, 30))
    runs = {os.path.basename(r.stem): r
            for r in sweep_snapshots.collect_runs(str(tmp_path))}
    assert len(runs["run_a"].snapshots) == 2
    assert len(runs["run_b"].snapshots) == 3


def test_apply_deletes_only_swept_runs_snapshots(tmp_path, monkeypatch, capsys):
    lay_down(tmp_path, "done")
    lay_down(tmp_path, "unfinished", final=False)
    lay_down(tmp_path, "live", age_s=60)

    monkeypatch.setattr("sys.argv", ["sweep_snapshots.py", "--runs-dir",
                                     str(tmp_path), "--apply"])
    sweep_snapshots.main()

    assert not list(tmp_path.glob("done.iter*.pt"))       # swept
    assert len(list(tmp_path.glob("unfinished.iter*.pt"))) == 3
    assert len(list(tmp_path.glob("live.iter*.pt"))) == 3
    assert (tmp_path / "done.pt").exists()                # handoff intact
    assert (tmp_path / "done.best.pt").exists()


def test_dry_run_is_the_default_and_deletes_nothing(tmp_path, monkeypatch, capsys):
    lay_down(tmp_path, "done")
    monkeypatch.setattr("sys.argv", ["sweep_snapshots.py", "--runs-dir",
                                     str(tmp_path)])
    sweep_snapshots.main()

    assert len(list(tmp_path.glob("done.iter*.pt"))) == 3
    assert "nothing deleted" in capsys.readouterr().out


def test_stem_filter_narrows_the_sweep(tmp_path, monkeypatch):
    lay_down(tmp_path, "keep_me")
    lay_down(tmp_path, "sweep_me")
    monkeypatch.setattr("sys.argv", ["sweep_snapshots.py", "--runs-dir",
                                     str(tmp_path), "--apply", "--stem", "sweep"])
    sweep_snapshots.main()

    assert not list(tmp_path.glob("sweep_me.iter*.pt"))
    assert len(list(tmp_path.glob("keep_me.iter*.pt"))) == 3
