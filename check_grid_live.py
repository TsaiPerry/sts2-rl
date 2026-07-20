"""Is a checkpoint's map-grid actually trainable, or is it the zero-splice?

The v3 -> v4 migration seats `run.map.grid` at exactly zero with no Adam
history. Resuming such a checkpoint lets 1890 columns -- half of `actor.0`'s
fan-in -- activate simultaneously, which collapsed the run twice. A freshly
initialised model has them at orthogonal-init scale instead, which is safe.

Exits 0 if the grid is live, 1 if it is the zero-splice. Do not hand-roll this
check with a `W[:, -1890:]` slice: the grid is columns 257..2147, so a
tail slice reads combat features and passes spuriously.

    py check_grid_live.py runs/sts2_column_v4.pt
"""
from __future__ import annotations

import sys

import torch

import train_torch
from sts2_rl import checkpoints
from sts2_rl.checkpoints import ModelSpec


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    spec = ModelSpec(env_kind=ckpt.get("env_kind", "run"), card_obs="hybrid",
                     arch=ckpt["arch"], hidden=tuple(ckpt["hidden"]))
    agent = checkpoints.make_model(spec, ckpt["obs_dim"], ckpt["n_actions"])
    (start, stop), = train_torch.segment_spans(agent, ["run.map.grid"])

    ok = True
    for head in ("actor", "critic"):
        block = ckpt["model"][f"{head}.0.weight"][:, start:stop]
        live = int(torch.count_nonzero(block))
        print(f"{head}.0.weight cols {start}..{stop}: {live}/{block.numel()} "
              f"non-zero, mean col-norm {block.norm(dim=0).mean():.5f}")
        # A live head is ~100% non-zero; the splice is exactly 0. Anything in
        # between means something partially masked it, which is also not safe
        # to resume, so require nearly all of it.
        ok = ok and live > 0.9 * block.numel()

    print("GRID LIVE - safe to resume" if ok else
          "GRID IS THE ZERO-SPLICE - resuming this would recreate the collapse")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
