"""Migrate an out-of-date run-scale checkpoint one schema hop forward.

    py migrate_ckpt.py runs/column.pt runs/column_migrated.pt

The hop is chosen from the source checkpoint's own ``obs_schema`` stamp:

  v3 → v4  schema v4 added run.boss.identity and run.map.grid/meta (the act
           boss and the whole act map) to the run observation. Those are pure
           feature additions, so migration splices zero columns into each
           trunk's first layer (and its Adam moments) at the new segments'
           positions — the migrated model computes bit-identical logits and
           values. See sts2_rl.checkpoints.migrate_checkpoint.

  v5 → v6  schema v6 changed no observation at all; it appended the
           out-of-combat potion block to the END of the action layout
           (run_env.POTION_BASE). Migration appends zero rows to the policy
           head and its Adam moments and touches nothing else, so the value
           function and the logits over every old action are preserved. See
           sts2_rl.checkpoints.migrate_checkpoint_actions.

v4 → v5 has no migration: it widened the leading phase segment, which shifts
every later observation index. That hop is a retrain.

The source checkpoint is never modified; the destination must not exist.
"""
from __future__ import annotations

import argparse
import os

import torch

from sts2_rl.checkpoints import migrate_checkpoint, migrate_checkpoint_actions


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Migrate a run-scale checkpoint one schema hop forward "
                    "(the source file is untouched).",
    )
    ap.add_argument("src", help="checkpoint to migrate (obs schema 3 or 5)")
    ap.add_argument("dst", help="where to write the migrated checkpoint")
    ap.add_argument("--card-obs", default="hybrid", choices=("hybrid", "features"),
                    help="the card_obs the checkpoint was trained with "
                         "(default: hybrid, the trainer's default)")
    args = ap.parse_args()

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        ap.error("src and dst are the same file; migration never overwrites")
    if os.path.exists(args.dst):
        ap.error(f"{args.dst} already exists; refusing to overwrite")

    ckpt = torch.load(args.src, map_location="cpu", weights_only=False)
    schema = ckpt.get("obs_schema")
    if schema == 3:
        migrated = migrate_checkpoint(ckpt, card_obs=args.card_obs)
    elif schema == 5:
        migrated = migrate_checkpoint_actions(ckpt, card_obs=args.card_obs)
    else:
        raise SystemExit(
            f"no migration from obs schema {schema}; this tool knows v3 -> v4 "
            f"and v5 -> v6 (v4 -> v5 shifted every observation index and is a "
            f"retrain).")
    torch.save(migrated, args.dst)
    # ASCII only: Windows consoles often decode as cp1252.
    print(f"{args.src} -> {args.dst}")
    print(f"  arch {migrated.get('arch', 'mlp')}   env {migrated['env_kind']}   "
          f"iteration {migrated.get('iteration', 0)}")
    print(f"  obs_dim {ckpt['obs_dim']} -> {migrated['obs_dim']}   "
          f"n_actions {ckpt['n_actions']} -> {migrated['n_actions']}   "
          f"obs_schema {schema} -> {migrated['obs_schema']}")


if __name__ == "__main__":
    main()
