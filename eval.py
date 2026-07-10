"""Model evaluation harness: win rate + lethal-probe accuracy (OBS_PLAN Phase 4).

Usage:
    py eval.py sts2_ppo --episodes 1000               # toy STS2CombatEnv model
    py eval.py sts2_ppo_full --env full               # full env: + probe accuracy
    py eval.py sts2_ppo_ablated --env full --ablated  # trained on AblatedObsEnv
    py eval.py --env full --baselines                 # no model: random + oracle

For --env full, probe accuracy is reported as a first-class metric alongside
win rate: the probes (sts2_rl/probes.py) are micro-scenarios where the right
move hinges on exact numbers — strike-lethal edges, block-or-die edges,
Weak/Vulnerable variants — so the score measures numeric grasp directly.
The toy env has its own 17-float observation, so probes don't apply there.
"""
import argparse
import io
import torch
import numpy as np

# PyTorch 2.12 changed its internal pth format in a way that breaks SB3 2.9's
# load path. SB3 passes a non-seekable zipfile stream and uses weights_only=True;
# both cause PyTorchFileReader to fail. Patch th.load inside SB3's save_util to
# read into a seekable BytesIO and use weights_only=False.
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
from sts2_rl import STS2CombatEnv, STS2FullCombatEnv
from sts2_rl.full_env import AblatedObsEnv
from sts2_rl.evaluation import (
    ablation_transform,
    evaluate_probes,
    evaluate_win_rate,
    masked_random_policy,
    model_policy,
    probe_summary,
)
from sts2_rl.probes import lethal_oracle


def evaluate_simple(model_path: str, n_episodes: int = 1000) -> None:
    """The original toy-env evaluation (STS2CombatEnv, 3 actions)."""
    env = STS2CombatEnv()
    model = MaskablePPO.load(model_path, env=env, device="cpu")

    final_hp = []
    wins = 0

    for _ in range(n_episodes):
        obs, info = env.reset()
        done = False
        while not done:
            action, _ = model.predict(obs, action_masks=env.action_masks(), deterministic=True)
            obs, _, terminated, truncated, info = env.step(int(action))
            done = terminated or truncated

        result = env._state.result
        if result.player_won:
            wins += 1
            final_hp.append(env._state.player.hp)
        else:
            final_hp.append(0)

    hp = np.array(final_hp)
    max_hp = env._state.player.max_hp

    print(f"Episodes : {n_episodes}")
    print(f"Win rate : {wins / n_episodes:.1%}")
    print()
    print(f"Final HP (all episodes, deaths = 0):")
    print(f"  Mean : {hp.mean():.1f} / {max_hp}")
    print(f"  Std  : {hp.std():.1f}")
    print(f"  Min  : {hp.min():.0f}")
    print(f"  Max  : {hp.max():.0f}")

    if wins > 0:
        hp_wins = hp[hp > 0]
        print(f"\nFinal HP (wins only):")
        print(f"  Mean : {hp_wins.mean():.1f} / {max_hp}")
        print(f"  Std  : {hp_wins.std():.1f}")
        print(f"  Min  : {hp_wins.min():.0f}")
        print(f"  Max  : {hp_wins.max():.0f}")


def evaluate_full(
    model_path: str | None,
    n_episodes: int,
    seed: int,
    ablated: bool,
    baselines: bool,
) -> None:
    """Full-env evaluation: win rate + probe accuracy for every policy row.

    Win rate runs on the env the policy was trained for (ablated models get an
    AblatedObsEnv); the probes always hand out raw observations, so ablated
    models see them through the same zeroing they were trained with.
    """
    # name -> (win-rate policy, win-rate env or None for default, probe policy)
    specs: dict[str, tuple] = {}
    if baselines or model_path is None:
        random_pol = masked_random_policy(seed)
        specs["masked-random"] = (random_pol, None, random_pol)
        specs["oracle"] = (lethal_oracle, None, lethal_oracle)
    if model_path is not None:
        # Inference on a 256x256 MLP: CPU avoids SB3's auto-to-GPU warning and
        # the host<->device copy per predict() call.
        model = MaskablePPO.load(model_path, device="cpu")
        if ablated:
            specs[f"model:{model_path}"] = (
                model_policy(model),
                AblatedObsEnv(STS2FullCombatEnv()),
                model_policy(model, ablation_transform()),
            )
        else:
            pol = model_policy(model)
            specs[f"model:{model_path}"] = (pol, None, pol)

    print(f"\n{n_episodes} episodes over the Act 1 pool, seed {seed}\n")
    header = f"{'policy':<28} {'win%':>6} {'turns':>6} {'hp_left':>8}   probes"
    print(header)
    print("-" * len(header))
    for name, (win_pol, env, probe_pol) in specs.items():
        report = evaluate_win_rate(win_pol, episodes=n_episodes, seed=seed, env=env)
        accuracy, results = evaluate_probes(probe_pol)
        print(
            f"{name:<28} {100 * report.win_rate:>5.1f}% {report.mean_turns:>6.1f} "
            f"{report.mean_hp_left:>8.1f}   {100 * accuracy:.0f}% = {probe_summary(results)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", default=None,
                        help="Path to saved model (e.g. sts2_ppo); optional with --baselines")
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--env", choices=["simple", "full"], default="simple",
                        help="'simple' = STS2CombatEnv (default, matches sts2_ppo); "
                             "'full' = STS2FullCombatEnv (matches train.py / sts2_full)")
    parser.add_argument("--seed", type=int, default=0, help="full env only")
    parser.add_argument("--ablated", action="store_true",
                        help="the model was trained on AblatedObsEnv observations (full env only)")
    parser.add_argument("--baselines", action="store_true",
                        help="also report masked-random + oracle rows (full env only)")
    args = parser.parse_args()

    if args.env == "full":
        if args.model is None and not args.baselines:
            parser.error("--env full needs a model, --baselines, or both")
        evaluate_full(args.model, args.episodes, args.seed, args.ablated, args.baselines)
    else:
        if args.model is None:
            parser.error("--env simple needs a model path")
        evaluate_simple(args.model, args.episodes)
