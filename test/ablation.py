"""OBS_PLAN Phase 4 (step 12) — the observation ablation.

Trains two MaskablePPO runs with identical seeds and hyperparameters — one on
the full schema-v2 observation, one on AblatedObsEnv (absolute-number and
preview features zeroed; same shape, same dynamics) — then reports win rate
and probe accuracy for both, plus a win-rate curve sampled during training.
This is the evidence that the numeric features earn their dimensions.

Usage:
    py test/ablation.py                          # 200k steps each arm
    py test/ablation.py --timesteps 500000 --episodes 500 --seed 3

Models are saved as sts2_ppo_full.zip / sts2_ppo_ablated.zip and can be
re-evaluated later with:  py eval.py sts2_ppo_ablated --env full --ablated
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback

from sts2_rl import STS2FullCombatEnv
from sts2_rl.full_env import AblatedObsEnv
from sts2_rl.evaluation import (
    ablation_transform,
    evaluate_probes,
    evaluate_win_rate,
    model_policy,
    probe_summary,
)


class WinRateCurve(BaseCallback):
    """Sample the win rate every `every` steps so the two arms can be compared
    as curves, not just endpoints."""

    def __init__(self, every: int, env_factory, episodes: int = 32, seed: int = 100_000):
        super().__init__()
        self._every = max(1, every)
        self._env_factory = env_factory
        self._episodes = episodes
        self._seed = seed
        self.points: list[tuple[int, float]] = []

    def _on_step(self) -> bool:
        if self.n_calls % self._every == 0:
            report = evaluate_win_rate(
                model_policy(self.model),
                episodes=self._episodes,
                seed=self._seed,
                env=self._env_factory(),
            )
            self.points.append((self.num_timesteps, report.win_rate))
            print(f"    [{self.num_timesteps:>8} steps] win rate {100 * report.win_rate:.1f}%")
        return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--timesteps", type=int, default=200_000)
    ap.add_argument("--episodes", type=int, default=200, help="final-eval episodes per arm")
    ap.add_argument("--curve-episodes", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    arms = {
        "full": lambda: STS2FullCombatEnv(),
        "ablated": lambda: AblatedObsEnv(STS2FullCombatEnv()),
    }
    outcomes = {}
    for arm, env_factory in arms.items():
        print(f"\n=== training arm: {arm} ({args.timesteps} steps, seed {args.seed}) ===")
        model = MaskablePPO("MlpPolicy", env_factory(), verbose=0, seed=args.seed)
        curve = WinRateCurve(args.timesteps // 10, env_factory, episodes=args.curve_episodes)
        model.learn(total_timesteps=args.timesteps, callback=curve)
        model.save(f"sts2_ppo_{arm}")

        report = evaluate_win_rate(
            model_policy(model), episodes=args.episodes, seed=args.seed + 777,
            env=env_factory(),
        )
        # The probe suite hands out raw observations; the ablated arm sees
        # them through the same zeroing it was trained with.
        probe_pol = model_policy(model, ablation_transform() if arm == "ablated" else None)
        accuracy, results = evaluate_probes(probe_pol)
        outcomes[arm] = (curve.points, report, accuracy, results)

    print("\n=== ablation summary (same seeds, same hyperparameters) ===\n")
    header = f"{'arm':<10} {'win%':>6} {'turns':>6} {'hp_left':>8}   probes"
    print(header)
    print("-" * len(header))
    for arm, (points, report, accuracy, results) in outcomes.items():
        print(
            f"{arm:<10} {100 * report.win_rate:>5.1f}% {report.mean_turns:>6.1f} "
            f"{report.mean_hp_left:>8.1f}   {100 * accuracy:.0f}% = {probe_summary(results)}"
        )
    print("\nwin-rate curves (timesteps: full% / ablated%):")
    full_pts = dict(outcomes["full"][0])
    abl_pts = dict(outcomes["ablated"][0])
    for t in sorted(set(full_pts) | set(abl_pts)):
        f = f"{100 * full_pts[t]:.1f}%" if t in full_pts else "-"
        a = f"{100 * abl_pts[t]:.1f}%" if t in abl_pts else "-"
        print(f"  {t:>8}: {f:>7} / {a:>7}")


if __name__ == "__main__":
    main()
