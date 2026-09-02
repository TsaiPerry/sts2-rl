"""Drive STS2RunEnv episodes and emit Monte-Carlo value-regression targets:
one (obs, return-to-go) record per visited run state. Sibling of harvest.py
(which emits pre-combat Snapshots); here we keep every step's obs + reward and,
at episode end, label each state with its discounted return-to-go under the
CURRENT (sampling) policy — the V^pi targets the critic value-fit regresses to
(spec 2026-08-31-critic-value-fit-design, Task 1 of the plan)."""
from __future__ import annotations
import argparse, faulthandler, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sts2_rl.run_env import (STS2RunEnv, masked_random_run_policy,
                             N_COMBAT_ACTIONS, run_obs_layout)
from tools.value_shards import returns_to_go, write_value_shard


def _make_policy(checkpoint, seed, device):
    import random
    if checkpoint is None:
        return masked_random_run_policy(random.Random(seed))
    from sts2_rl.evaluation import load_torch_policy
    env = STS2RunEnv()
    policy, _ = load_torch_policy(checkpoint, env_kind="run", env=env,
                                  device=device, sample=True, seed=seed)
    return policy


def harvest_values(*, episodes, seed, out, gamma=0.999, checkpoint=None,
                   device="cpu", ascension=10, shard_size=4096,
                   watchdog_secs=120.0):
    layout = run_obs_layout("hybrid")
    policy = _make_policy(checkpoint, seed, device)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)

    buf_f, buf_i, buf_g, buf_c = [], [], [], []
    shard_idx = [0]; n_states = [0]; n_combat = [0]

    def flush():
        if not buf_f:
            return
        write_value_shard(out / f"shard-{shard_idx[0]:05d}.npz",
                          np.stack(buf_f), np.stack(buf_i),
                          np.concatenate(buf_g), np.concatenate(buf_c))
        shard_idx[0] += 1
        buf_f.clear(); buf_i.clear(); buf_g.clear(); buf_c.clear()

    for ep in range(episodes):
        env = STS2RunEnv(ascension=ascension)
        obs, _info = env.reset(seed=seed + ep)
        ep_f, ep_i, ep_c, ep_r = [], [], [], []
        terminated = truncated = False
        while not (terminated or truncated):
            mask = env.action_masks()
            action = int(policy(env, obs, mask))
            if not mask[action]:
                action = int(np.flatnonzero(mask)[0])
            ep_f.append(np.asarray(obs["f"], np.float16))
            ep_i.append(np.asarray(obs["i"], np.int32))
            ep_c.append(bool(mask[:N_COMBAT_ACTIONS].any()))
            faulthandler.dump_traceback_later(watchdog_secs, exit=True)
            try:
                obs, reward, terminated, truncated, _info = env.step(action)
            finally:
                faulthandler.cancel_dump_traceback_later()
            ep_r.append(float(reward))
        env.close()
        g = returns_to_go(ep_r, gamma)
        for t in range(len(ep_f)):
            buf_f.append(ep_f[t]); buf_i.append(ep_i[t])
            buf_g.append(np.array([g[t]], np.float64))
            buf_c.append(np.array([ep_c[t]], np.bool_))
            n_states[0] += 1; n_combat[0] += int(ep_c[t])
            if len(buf_f) >= shard_size:
                flush()
    flush()

    prov = {"obs_schema": 13, "card_obs": "hybrid",
            "f_dim": int(layout.f_dim), "i_dim": int(layout.i_dim),
            "gamma": gamma, "ascension": ascension, "seed": seed,
            "episodes": episodes, "checkpoint": checkpoint,
            "states": n_states[0], "combat_states": n_combat[0]}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2))
    return prov


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gamma", type=float, default=0.999)
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--ascension", type=int, default=10)
    ap.add_argument("--shard-size", type=int, default=4096)
    ap.add_argument("--watchdog-secs", type=float, default=120.0)
    a = ap.parse_args(argv)
    prov = harvest_values(episodes=a.episodes, seed=a.seed, out=a.out,
                          gamma=a.gamma, checkpoint=a.checkpoint,
                          device=a.device, ascension=a.ascension,
                          shard_size=a.shard_size, watchdog_secs=a.watchdog_secs)
    print(json.dumps(prov, indent=2))
    return prov


if __name__ == "__main__":
    main()
