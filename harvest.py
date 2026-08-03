"""harvest.py -- CLI that drives STS2RunEnv episodes and records a start-state
Snapshot (sts2_rl/snapshots.py) for every combat entered, for the phase-3
combat-env snapshot mode (R11).

    py harvest.py --episodes 400 --seed 0 --out runs/snapshots/random-v1.jsonl
    py harvest.py --episodes 50 --seed 0 --out out.jsonl --checkpoint runs/sts2_run_torch.pt

By default the driving policy is `run_env.masked_random_run_policy` (a fresh
`random.Random(seed)` per process); `--checkpoint` loads a `train_torch.py`
run-env checkpoint instead, via `evaluation.load_torch_policy` (the same
entry point `eval.py --env run --checkpoint ...` uses), run in SAMPLING mode
(`sample=True`) rather than greedy -- a greedy policy is deterministic given
the checkpoint, so every episode from the same model would make near-
identical choices and the harvested snapshots would collapse onto one
narrow slice of state space instead of covering a diverse one.

Every combat any episode enters fires `RunDriver.on_combat_start` (locked
decision 4, driver.py); this CLI turns that firing into a `Snapshot`
(`snapshots.snapshot_from_run`) with `provenance` OVERWRITTEN to real values
-- `snapshot_from_run` itself can only fill `seed` from `RunState.string_seed`
(unset here -- `STS2RunEnv._make_run_state` builds a bare, non-string-seeded
run) and defaults `episode_decisions` to a 0 placeholder (see that function's
own docstring), so this module is exactly the "harvester" its docstring
names as the intended owner of both real values.

Snapshots are appended to `--out` one at a time, each write flushed
immediately, so a hard abort (including the watchdog below) loses nothing
already harvested. `snapshots.save_snapshots` writes a whole iterable in one
open/close and is not built for incremental, crash-safe appends -- rather
than editing that module (out of this lane's ownership), `_SnapshotAppender`
below reuses its private `_snapshot_to_json`/`SNAPSHOT_SCHEMA` so the emitted
JSONL is byte-for-byte the same format `save_snapshots`/`load_snapshots`
agree on, without duplicating that shape by hand.

Watchdog: the run-env `step()` hang (phase-3 Global Constraints; owned by
the concurrent source-fidelity audit -- this CLI never diagnoses or works
around it) means a harvest can wedge inside a single `env.step()` call
forever. `faulthandler.dump_traceback_later(watchdog_secs, exit=True)` is
re-armed before every step and cancelled right after it returns; if a step
ever takes longer than `--watchdog-secs`, the handler dumps every thread's
stack to `--log` (or stderr) and calls `os._exit(1)` -- the process dies
loudly, mid-episode, with whatever was already flushed to `--out` intact.
This deliberately deviates from a literal reading of "faulthandler's
default": `dump_traceback_later`'s actual default is `exit=False` (dump and
keep running), which would NOT make the process die -- only `exit=True`
does that, so it is passed explicitly (see report for the premise check).
NO timeout-and-continue: a trip is fatal, not skipped.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, TextIO

import numpy as np

from sts2_rl.monsters import Encounter
from sts2_rl.run import RunState
from sts2_rl.run_env import STS2RunEnv, masked_random_run_policy
from sts2_rl.snapshots import (
    SNAPSHOT_SCHEMA,
    Snapshot,
    _snapshot_to_json,
    snapshot_from_run,
)


class _SnapshotAppender:
    """Streams `Snapshot`s to `path` as JSON Lines, one `save_snapshots`-
    format line at a time, flushing (and fsync-ing) after every write so an
    abort at any point leaves every already-written line durable and the
    file loadable by `snapshots.load_snapshots` as-is (no trailing partial
    line -- each write is one complete, newline-terminated JSON object)."""

    def __init__(self, path: "str | Path") -> None:
        self.path = Path(path)
        self._fh: TextIO = self.path.open("w", encoding="utf-8")
        self._fh.write(json.dumps({"snapshot_schema": SNAPSHOT_SCHEMA}))
        self._fh.write("\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self.count = 0

    def append(self, snap: Snapshot) -> None:
        self._fh.write(json.dumps(_snapshot_to_json(snap)))
        self._fh.write("\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self.count += 1

    def close(self) -> None:
        self._fh.close()


def _make_policy(checkpoint: "str | None", seed: int, device: str = "cpu"):
    """`(env, obs, mask) -> action` policy factory. Default:
    `masked_random_run_policy` over a fresh `random.Random(seed)`.
    `--checkpoint` loads a `train_torch.py` run-env checkpoint through
    `evaluation.load_torch_policy` (the SAME loader `eval.py --env run
    --checkpoint ...` uses -- verified by reading eval.py's `make_run_env`/
    `evaluate_run_report` call sites, not assumed), in SAMPLING mode
    (`sample=True`): greedy (`sample=False`, the default there) always picks
    the mode of the trained distribution, so every one of --episodes runs
    would make nearly the same choices from the same starting state and the
    harvested dataset would collapse onto one narrow trajectory instead of
    covering a diverse one -- exactly the shallow-coverage failure this CLI
    exists to avoid even before a trained checkpoint exists (see the module
    docstring's masked-random default)."""
    if checkpoint is None:
        return masked_random_run_policy(random.Random(seed))
    from sts2_rl.evaluation import load_torch_policy

    env = STS2RunEnv()
    policy, _ckpt = load_torch_policy(
        checkpoint, env_kind="run", env=env, device=device,
        sample=True, seed=seed,
    )
    return policy


def _make_env(on_combat_start) -> STS2RunEnv:
    return STS2RunEnv(on_combat_start=on_combat_start)


def harvest(
    *,
    episodes: int,
    seed: int,
    out: "str | Path",
    checkpoint: "str | None" = None,
    watchdog_secs: float = 120.0,
    log: "str | Path | None" = None,
    device: str = "cpu",
) -> dict[str, Any]:
    """Drives `episodes` seeded `STS2RunEnv` episodes (`seed .. seed +
    episodes - 1`), appending a `Snapshot` to `out` for every combat any
    episode enters. Returns a summary dict (also printed by `main`).

    Structured as a plain function, not folded into `main`, so tests can
    call it directly without going through `sys.argv`/subprocess (lane-rules
    requirement)."""
    appender = _SnapshotAppender(out)
    log_fh: TextIO = (
        Path(log).open("a", encoding="utf-8") if log is not None else sys.stderr
    )
    watchdog_fh: TextIO = log_fh

    policy = _make_policy(checkpoint, seed, device=device)

    floors: list[int] = []
    acts: list[int] = []
    combats_entered = 0

    try:
        for ep in range(episodes):
            episode_seed = seed + ep
            # Mutable so the on_combat_start closure (fired synchronously
            # inside the driver's greenlet, mid- env.step()) always reads
            # the count of decisions RESOLVED before the step currently in
            # flight -- incremented once per completed env.step() below, so
            # a combat that opens on this very step sees the count as of
            # just before it, not after.
            decisions_so_far = [0]

            def _on_combat_start(run: RunState, encounter: Encounter) -> None:
                nonlocal combats_entered
                snap = snapshot_from_run(run, encounter)
                snap.provenance["seed"] = episode_seed
                snap.provenance["floor"] = run.total_floor
                snap.provenance["episode_decisions"] = decisions_so_far[0]
                appender.append(snap)
                combats_entered += 1

            env = _make_env(_on_combat_start)
            obs, info = env.reset(seed=episode_seed)
            max_floor = int(info.get("floor", 0))
            max_act = int(info.get("act", 0))
            terminated = truncated = False
            step_in_episode = 0
            while not (terminated or truncated):
                mask = env.action_masks()
                action = int(policy(env, obs, mask))
                if not mask[action]:
                    action = int(np.flatnonzero(mask)[0])
                faulthandler.dump_traceback_later(
                    watchdog_secs, file=watchdog_fh, exit=True)
                try:
                    obs, _reward, terminated, truncated, info = env.step(action)
                finally:
                    faulthandler.cancel_dump_traceback_later()
                step_in_episode += 1
                decisions_so_far[0] += 1
                max_floor = max(max_floor, int(info.get("floor", 0)))
                max_act = max(max_act, int(info.get("act", 0)))
                log_fh.write(
                    f"{episode_seed}\t{ep}\t{decisions_so_far[0]}\n")
                log_fh.flush()
            env.close()
            floors.append(max_floor)
            acts.append(max_act)
    finally:
        appender.close()
        if log is not None:
            log_fh.close()

    floor_hist = Counter(floors)
    act_hist = Counter(acts)
    summary = {
        "episodes": episodes,
        "combats_entered": combats_entered,
        "snapshots_written": appender.count,
        "floor_histogram": dict(sorted(floor_hist.items())),
        "act_histogram": dict(sorted(act_hist.items())),
    }
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"episodes played: {summary['episodes']}")
    print(f"snapshots written: {summary['snapshots_written']}")
    print(f"combats entered: {summary['combats_entered']}")
    print("floor histogram:")
    for floor, n in summary["floor_histogram"].items():
        print(f"  floor {floor}: {n}")
    print("act histogram:")
    for act, n in summary["act_histogram"].items():
        print(f"  act {act}: {n}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Drive STS2RunEnv episodes and harvest a pre-combat Snapshot "
            "(sts2_rl/snapshots.py) for every combat entered, for the "
            "combat env's snapshot start-state mode."
        ),
    )
    p.add_argument("--episodes", type=int, required=True,
                    help="number of episodes; seeds are seed .. seed+episodes-1")
    p.add_argument("--seed", type=int, required=True,
                    help="first episode's seed")
    p.add_argument("--out", type=str, required=True,
                    help="output JSONL path (overwritten)")
    p.add_argument("--checkpoint", type=str, default=None,
                    help=(
                        "train_torch.py run-env checkpoint; if omitted, "
                        "drives with masked_random_run_policy. Runs in "
                        "SAMPLING mode, not greedy -- greedy would collapse "
                        "every episode from a given model onto nearly the "
                        "same trajectory, defeating the point of a diverse "
                        "harvest."
                    ))
    p.add_argument("--device", type=str, default="cpu",
                    help="torch device for --checkpoint inference")
    p.add_argument("--watchdog-secs", type=float, default=120.0,
                    help=(
                        "faulthandler.dump_traceback_later timeout, re-armed "
                        "every step; a trip dumps every thread's stack and "
                        "kills the process (os._exit) -- the run-env step() "
                        "hang is a known open issue this CLI never works "
                        "around."
                    ))
    p.add_argument("--log", type=str, default=None,
                    help=(
                        "path for the per-step (seed, episode, decision) "
                        "log and the watchdog's stack dump; defaults to "
                        "stderr"
                    ))
    return p


def main(argv: "list[str] | None" = None) -> dict[str, Any]:
    args = build_arg_parser().parse_args(argv)
    summary = harvest(
        episodes=args.episodes,
        seed=args.seed,
        out=args.out,
        checkpoint=args.checkpoint,
        watchdog_secs=args.watchdog_secs,
        log=args.log,
        device=args.device,
    )
    _print_summary(summary)
    return summary


if __name__ == "__main__":
    main()
