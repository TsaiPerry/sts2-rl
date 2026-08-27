"""dump_layout_keys_v24 -- one-shot discovery for migrate_runobs_v24.

Prints (1) the state-dict keys + shapes of a seed checkpoint, (2) the
CURRENT (live) run-scale entset segment plan with block indices, so the
migration's key map and splice offsets are read off reality, not guessed.

Usage:
    .venv\\Scripts\\python.exe tools\\dump_layout_keys_v24.py runs\\sts2_run_torch_v23_s26.pt
"""
import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from sts2_rl import models
from sts2_rl.checkpoints import ModelSpec, model_obs_layout


def main() -> None:
    ck = torch.load(sys.argv[1], map_location="cpu", weights_only=False)
    print("== checkpoint stamps ==")
    for k in ("obs_schema", "head_version", "arch", "env_kind", "obs_dim",
              "shared_encoder", "hidden"):
        print(f"  {k} = {ck.get(k)}")
    print("== state dict (name, shape) ==")
    for name, t in ck["model"].items():
        print(f"  {name}  {tuple(t.shape)}")

    spec = ModelSpec("run", arch="entset", hidden=tuple(ck.get("hidden", (256, 256))),
                      shared_encoder=ck.get("shared_encoder", True))
    f_segs, i_segs = model_obs_layout(spec)
    print(f"== live f_dim={sum(w for _, w in f_segs)} i_dim={sum(w for _, w in i_segs)} ==")
    row_blocks, raw_f_segments = models.entset_segment_plan(f_segs, i_segs)
    print("== current (live) row-block plan (index, name, cap, n_float, vocabs) ==")
    for idx, (name, cap, n_float, vocabs) in enumerate(row_blocks):
        print(f"  {idx}: {name}  cap={cap} n_float={n_float} vocabs={vocabs}")
    print("== raw (non-row-block) float segments, in encoder-out tail order ==")
    for name, width in raw_f_segments:
        print(f"  {name}  width={width}")


if __name__ == "__main__":
    main()
