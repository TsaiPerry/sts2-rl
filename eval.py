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
from sts2_rl import STS2CombatEnv

def evaluate(model_path: str, n_episodes: int = 1000) -> None:
    env = STS2CombatEnv()
    model = MaskablePPO.load(model_path, env=env)

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="Path to saved model (e.g. sts2_ppo)")
    parser.add_argument("--episodes", type=int, default=1000)
    args = parser.parse_args()
    evaluate(args.model, args.episodes)
