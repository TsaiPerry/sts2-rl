"""Losslessly migrate a v3 run-scale checkpoint to obs schema v4.

    py migrate_ckpt.py runs/column.pt runs/column_v4.pt

Schema v4 added run.boss.identity and run.map.grid/meta (the act boss and
the whole act map) to the run observation. Those are pure feature
additions, so migration splices zero columns into each trunk's first layer
(and its Adam moments) at the new segments' positions — the migrated model
computes bit-identical logits/values and resumes training via --resume as
if nothing happened, then learns to use the new inputs. See
sts2_rl.checkpoints.migrate_checkpoint.

The source checkpoint is never modified; the destination must not exist.
"""
from __future__ import annotations

import argparse
import os

import torch

from sts2_rl.checkpoints import migrate_checkpoint


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Migrate a v3 run-scale checkpoint to obs schema v4 "
                    "(function-preserving; the source file is untouched).",
    )
    ap.add_argument("src", help="v3 checkpoint to migrate")
    ap.add_argument("dst", help="where to write the migrated v4 checkpoint")
    ap.add_argument("--card-obs", default="hybrid", choices=("hybrid", "features"),
                    help="the card_obs the checkpoint was trained with "
                         "(default: hybrid, the trainer's default)")
    args = ap.parse_args()

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        ap.error("src and dst are the same file; migration never overwrites")
    if os.path.exists(args.dst):
        ap.error(f"{args.dst} already exists; refusing to overwrite")

    ckpt = torch.load(args.src, map_location="cpu", weights_only=False)
    migrated = migrate_checkpoint(ckpt, card_obs=args.card_obs)
    torch.save(migrated, args.dst)
    # ASCII only: Windows consoles often decode as cp1252.
    print(f"{args.src} -> {args.dst}")
    print(f"  arch {migrated.get('arch', 'mlp')}   env {migrated['env_kind']}   "
          f"iteration {migrated.get('iteration', 0)}")
    print(f"  obs_dim {ckpt['obs_dim']} -> {migrated['obs_dim']}   "
          f"obs_schema 3 -> 4")


if __name__ == "__main__":
    main()
