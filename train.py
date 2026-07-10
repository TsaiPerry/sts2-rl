"""Train a MaskablePPO agent on the full STS2 combat env.

    py train.py                          # train on the whole Act 1 pool
    py train.py --encounter fuzzy_wurm_weak --timesteps 200000   # one fight
    py train.py --resume sts2_full       # continue from a saved model

Evaluate a saved model with:  py eval.py sts2_full --env full
"""
from __future__ import annotations

import argparse
import io
import os

# SB3's load path breaks on newer PyTorch (non-seekable zip stream +
# weights_only=True). Patch th.load in save_util before importing SB3 — same
# shim eval.py uses; only needed for --resume, but harmless otherwise.
import torch
import stable_baselines3.common.save_util as _sb3_save_util


class _TorchProxy:
    def __getattr__(self, name):
        return getattr(torch, name)

    def load(self, file, map_location=None, **kwargs):
        kwargs["weights_only"] = False
        if hasattr(file, "read"):
            file = io.BytesIO(file.read())
        return torch.load(file, map_location=map_location, **kwargs)


_sb3_save_util.th = _TorchProxy()

from sb3_contrib import MaskablePPO
from stable_baselines3.common.monitor import Monitor

from sts2_rl import STS2FullCombatEnv
from sts2_rl.monsters.overgrowth import ENCOUNTERS as OVERGROWTH


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=1_000_000)
    ap.add_argument("--encounter", default=None,
                    help="Overgrowth encounter key to fix (default: sample the whole act)")
    ap.add_argument("--card-obs", choices=["hybrid", "features"], default="hybrid")
    ap.add_argument("--resume", default=None, help="path to a saved model to continue")
    ap.add_argument("--save", default="sts2_full")
    args = ap.parse_args()

    encounter = OVERGROWTH[args.encounter] if args.encounter else None
    env = Monitor(STS2FullCombatEnv(encounter=encounter, card_obs=args.card_obs))

    # device="cpu" explicitly: SB3's "auto" would move MlpPolicy to the GPU and
    # then warn that PPO-with-an-MLP is slower there than on the CPU.
    if args.resume and os.path.exists(args.resume + ".zip"):
        model = MaskablePPO.load(args.resume, env=env, device="cpu")
        print(f"Resuming from {args.resume}.zip")
    else:
        model = MaskablePPO("MlpPolicy", env, verbose=1, device="cpu")
        print("Starting fresh.")

    model.learn(total_timesteps=args.timesteps)
    model.save(args.save)
    print(f"Saved to {args.save}.zip")


if __name__ == "__main__":
    main()
