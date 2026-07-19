"""Per-encounter evaluation: average model performance vs each non-boss
Overgrowth enemy.

Loads a raw-PyTorch checkpoint (the current training path — ``train_torch.py`` /
``sts2_rl.models``, saved to ``runs/sts2_torch.pt``) and rolls it, deterministically,
over every non-boss Act-1 (Overgrowth) encounter for N episodes each, printing
win rate + mean turns + mean HP left per encounter and an overall average.

    py test/eval.py                                   # runs/sts2_torch.pt, 50 eps each
    py test/eval.py --model runs/sts2_torch.pt --episodes 50
    py test/eval.py --baseline                        # masked-random floor, no model

Non-boss = every key in ``overgrowth.ENCOUNTERS`` except ``BOSS_ENCOUNTER_KEYS``
(the same split ``full_env.DEFAULT_ENCOUNTERS`` trains on).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

# Allow ``py test/eval.py`` from the repo root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sts2_rl import STS2FullCombatEnv
from sts2_rl.evaluation import evaluate_win_rate, load_torch_policy, masked_random_policy
from sts2_rl.monsters.overgrowth import BOSS_ENCOUNTER_KEYS, ENCOUNTERS

EPISODES = 50


def non_boss_encounters() -> dict:
    """The non-boss Overgrowth encounters, in registry order."""
    return {k: e for k, e in ENCOUNTERS.items() if k not in BOSS_ENCOUNTER_KEYS}


def load_model_policy(model_path: str, device: str = "cpu"):
    """A train_torch.py checkpoint as a deterministic ``(env, obs, mask) -> int``
    policy — greedy over the masked logits. Arch dispatch, schema checking and
    model construction all live in ``sts2_rl.evaluation`` / ``sts2_rl.checkpoints``,
    shared with ``eval.py``."""
    policy, _ckpt = load_torch_policy(
        model_path, env_kind="combat", env=STS2FullCombatEnv(), device=device)
    return policy


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="runs/sts2_torch.pt",
                    help="path to a train_torch.py checkpoint (default: runs/sts2_torch.pt)")
    ap.add_argument("--episodes", type=int, default=EPISODES,
                    help="episodes per encounter (default: 50)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--baseline", action="store_true",
                    help="evaluate the masked-random floor instead of a model")
    args = ap.parse_args()

    if args.baseline:
        policy = masked_random_policy(args.seed)
        label = "masked-random"
    else:
        if not os.path.exists(args.model):
            raise SystemExit(
                f"model not found: {args.model}\n"
                f"  train one with `py train_torch.py`, or pass --baseline for the "
                f"random floor.")
        policy = load_model_policy(args.model, args.device)
        label = args.model

    encounters = non_boss_encounters()
    print(f"\n{label}: {args.episodes} episodes per encounter, "
          f"{len(encounters)} non-boss Overgrowth encounters, seed {args.seed}\n")
    header = f"{'encounter':<24} {'win%':>6} {'turns':>7} {'hp_left':>8}"
    print(header)
    print("-" * len(header))

    win_rates, hp_lefts, turns = [], [], []
    for key, enc in encounters.items():
        env = STS2FullCombatEnv(encounter=enc)
        report = evaluate_win_rate(
            policy, episodes=args.episodes, seed=args.seed, env=env)
        win_rates.append(report.win_rate)
        hp_lefts.append(report.mean_hp_left)
        turns.append(report.mean_turns)
        print(f"{key:<24} {100 * report.win_rate:>5.1f}% "
              f"{report.mean_turns:>7.1f} {report.mean_hp_left:>8.1f}")

    print("-" * len(header))
    print(f"{'AVERAGE':<24} {100 * float(np.mean(win_rates)):>5.1f}% "
          f"{float(np.mean(turns)):>7.1f} {float(np.mean(hp_lefts)):>8.1f}")


if __name__ == "__main__":
    main()
