"""Formerly: migrate an out-of-date run-scale checkpoint one schema hop
forward. As of the phase-1 schema bump THIS
TOOL CANNOT MIGRATE ANYTHING — running it always exits with an error.

The run observation moved from a flat array to an ``"f"``/``"i"`` Dict, a
different Gym space type, and there is no v6 -> v7 weight migration for that
change (see ``sts2_rl.checkpoints.check_checkpoint``, which now refuses every
pre-v7 checkpoint before either migration function below could be reached).
Both hops this tool used to offer are unreachable dead code kept only per
CLAUDE.md §3 (this file doesn't delete pre-existing code it didn't write):

  v3 → v4  sts2_rl.checkpoints.migrate_checkpoint — used to splice zero
           columns for the new run.boss.identity / run.map.grid+meta
           segments. No longer buildable: the segments it spliced against
           were a flat-array layout.

  v5 → v6  sts2_rl.checkpoints.migrate_checkpoint_actions — used to append
           zero rows to the policy head for the new out-of-combat potion
           action block. No longer buildable: RUN_OBS_SCHEMA_VERSION moved
           past its v6 target without that target being rebuilt.

If you are holding a schema 2-6 checkpoint, there is no lossless path
forward for it. Start training over with --fresh.
"""
from __future__ import annotations

import argparse
import os

import torch

from sts2_rl.checkpoints import migrate_checkpoint, migrate_checkpoint_actions


def main() -> None:
    ap = argparse.ArgumentParser(
        description="No checkpoint can be migrated any more (phase-1 schema "
                    "bump) — this always exits "
                    "with an error explaining why. Kept for the error message "
                    "only; see the module docstring. Start --fresh instead.",
    )
    ap.add_argument("src", help="checkpoint to inspect (never migrated; the "
                                "obs_schema stamp only decides which error "
                                "you get)")
    ap.add_argument("dst", help="unused — no destination is ever written")
    ap.add_argument("--card-obs", default="hybrid", choices=("hybrid", "features"),
                    help="unused — plumbed through to the dead migration "
                         "functions for their own error messages only")
    args = ap.parse_args()

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        ap.error("src and dst are the same file; migration never overwrites")
    if os.path.exists(args.dst):
        ap.error(f"{args.dst} already exists; refusing to overwrite")

    # Every branch below raises SystemExit — nothing is ever written to
    # args.dst. schema 3/5 delegate to the (now-stub) migration functions so
    # the error names the exact reason THAT hop is dead; anything else gets
    # this tool's own message. Kept as a dispatch rather than one flat
    # message so each stale schema still gets its most specific explanation.
    ckpt = torch.load(args.src, map_location="cpu", weights_only=False)
    schema = ckpt.get("obs_schema")
    if schema == 3:
        migrate_checkpoint(ckpt, card_obs=args.card_obs)
    elif schema == 5:
        migrate_checkpoint_actions(ckpt, card_obs=args.card_obs)
    else:
        raise SystemExit(
            f"no migration from obs schema {schema} (or any other schema — "
            f"the phase-1 schema bump left no migration path onto the "
            f"current one); start training over with --fresh.")


if __name__ == "__main__":
    main()
