"""Raw-PyTorch masked PPO for STS2FullCombatEnv / STS2RunEnv (no stable-baselines).

    py train_torch.py                                       # combat env, Act-1 pool; auto-resumes runs/sts2_torch.pt if present
    py train_torch.py --fresh                               # ignore any existing checkpoint, start over
    py train_torch.py --encounter fuzzy_wurm_weak --timesteps 500000
    py train_torch.py --resume runs/other.pt                # continue from a specific checkpoint
    py train_torch.py --env run                             # full-run env (map/events/shops/rewards + combat);
                                                            # saves runs/sts2_run_torch.pt by default
    py train_torch.py --env column                          # phase-1 curriculum: full runs on randomized
                                                            # single-column maps, floor-only reward; its
                                                            # checkpoint later resumes on --env run

By default a run *continues* the checkpoint at ``--save`` if the file already
exists (so re-running ``py train_torch.py`` trains the same model further instead
of clobbering it); pass ``--fresh`` to start a new model, or ``--resume PATH`` to
continue from a different checkpoint.

This is the baseline loop from the plan: a plain MLP torso (``sts2_rl.models``)
trained with PPO. The one thing MaskablePPO did for us — applying
``env.action_masks()`` — we now do ourselves, at BOTH act-time and update-time,
so the ratio and entropy are computed over the same masked distribution the
agent acted under.

Single-file, hand-vectorized over ``--n-envs`` synchronous envs. Everything the
architecture plan cares about is swappable without touching this file: change
the torso in ``models.py``; change the observation in ``full_env.py``. The loop
only depends on ``reset`` / ``step`` / ``action_masks`` and the model's three
methods.

Runs on CPU by default, and that is usually the *fast* choice: a 256x256 MLP
over 8 Python-stepped envs is bottlenecked on env stepping and per-step
host<->device copies, not on matmul, so a GPU tends to be slower here. SB3
warns about the same thing for MlpPolicy PPO. ``--device cuda`` is there for
when the torso grows big enough to pay for the transfers -- measure ``sps``
before and after rather than assuming.
"""
from __future__ import annotations

import argparse
import os
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn

from sts2_rl import STS2FullCombatEnv
from sts2_rl.full_env import OBS_SCHEMA_VERSION
from sts2_rl.models import EntityActorCritic, MaskedActorCritic
from sts2_rl.monsters.overgrowth import ENCOUNTERS as OVERGROWTH


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    # experiment
    ap.add_argument("--env", choices=["combat", "run", "column"], default="column",
                    help="combat = STS2FullCombatEnv (single fights); "
                         "run = STS2RunEnv (whole runs: map, events, shops, "
                         "rewards, every decision policy-controlled); "
                         "column = STS2CurriculumRunEnv (whole runs on "
                         "randomized single-column maps, floor-only reward — "
                         "the phase-1 curriculum; checkpoints resume on "
                         "--env run for phase 2)")
    ap.add_argument("--acts", nargs="+", default=None,
                    help="run/column envs only: the act list (default: rolled "
                         "per episode over the ported acts, e.g. overgrowth|"
                         "underdocks then hive)")
    ap.add_argument("--timesteps", type=int, default=1_000_000)
    ap.add_argument("--encounter", default=None,
                    help="combat env only: Overgrowth encounter key to fix "
                         "(default: sample the whole act)")
    ap.add_argument("--card-obs", choices=["hybrid", "features"], default="hybrid")
    ap.add_argument("--arch", choices=["mlp", "entity"], default="mlp",
                    help="mlp = MaskedActorCritic (flat trunks over the raw "
                         "obs); entity = EntityActorCritic (per-segment "
                         "embedding encoders over the same obs). Checkpoints "
                         "are arch-stamped — switching arch is a full retrain")
    ap.add_argument("--enemy-hp-reward", type=float, default=0.0,
                    help="dense damage-dealt reward weight (0 = HP-delta + win only)")
    ap.add_argument("--win-hp-bonus", type=float, default=1.0,
                    help="terminal win bonus scaled by final HP fraction: win reward is "
                         "reward_win + win_hp_bonus*(hp/max_hp), so clean wins beat sloppy ones "
                         "(0 = flat win bonus, the old behavior)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cpu",
                    help="cpu (default, usually fastest here), cuda, or auto")
    ap.add_argument("--save", default=None,
                    help="checkpoint path (default: runs/sts2_torch.pt for "
                         "--env combat, runs/sts2_run_torch.pt for --env run, "
                         "runs/sts2_column_torch.pt for --env column)")
    ap.add_argument("--resume", default=None,
                    help="continue from this checkpoint (default: auto-resume --save if it exists)")
    ap.add_argument("--fresh", action="store_true",
                    help="start a new model even if a checkpoint exists at --save")
    ap.add_argument("--save-every", type=int, default=50, help="iterations between checkpoints")
    # rollout / PPO
    ap.add_argument("--n-envs", type=int, default=8)
    ap.add_argument("--n-steps", type=int, default=512, help="rollout length per env")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--gamma", type=float, default=None,
                    help="discount (default: 0.99 for --env combat, 0.999 for "
                         "the run-scale envs — a full run is 1000+ steps, and "
                         "floor-only reward needs deaths to stay visible from "
                         "the HP loss that caused them)")
    ap.add_argument("--gae-lambda", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--minibatches", type=int, default=8)
    ap.add_argument("--ent-coef", type=float, default=0.01)
    ap.add_argument("--vf-coef", type=float, default=0.5)
    ap.add_argument("--max-grad-norm", type=float, default=0.5)
    ap.add_argument("--target-kl", type=float, default=None,
                    help="early-stop the epoch loop if approx_kl exceeds this")
    ap.add_argument("--hidden", type=int, nargs="+", default=[256, 256])
    args = ap.parse_args()
    if args.save is None:
        args.save = {
            "combat": "runs/sts2_torch.pt",
            "run": "runs/sts2_run_torch.pt",
            "column": "runs/sts2_column_torch.pt",
        }[args.env]
    if args.gamma is None:
        args.gamma = 0.99 if args.env == "combat" else 0.999
    if args.env != "combat" and args.encounter:
        raise SystemExit("--encounter applies to --env combat only.")
    if args.env == "combat" and args.acts:
        raise SystemExit("--acts applies to the run-scale envs only.")
    return args


def resolve_device(requested: str) -> torch.device:
    """Map ``--device`` onto a real device, and say out loud what we picked.

    ``torch.cuda.is_available()`` is False both when the wheel has no CUDA
    support compiled in and when it has support but no GPU is visible. Those
    need different fixes, so they get different messages.
    """
    cpu_only_wheel = torch.version.cuda is None

    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(requested)

    if device.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit(
            f"--device cuda requested, but torch reports no usable GPU.\n"
            + (f"  torch {torch.__version__} is a CPU-only build. Reinstall from a\n"
               f"  CUDA wheel index -- see the PyTorch section of requirements.txt.\n"
               if cpu_only_wheel else
               f"  torch {torch.__version__} has CUDA {torch.version.cuda} support, but no\n"
               f"  GPU is visible. Check the driver and CUDA_VISIBLE_DEVICES.\n")
        )

    # Printed unconditionally: a CPU-only wheel on a GPU box is otherwise
    # indistinguishable from a working GPU setup until you notice the sps.
    build = torch.version.cuda or "cpu-only build"
    print(f"torch {torch.__version__} [{build}]  device: {device}", flush=True)
    return device


def make_env(args: argparse.Namespace):
    if args.env == "column":
        from sts2_rl.curriculum_env import STS2CurriculumRunEnv

        # Floor-only reward defaults live on the env class; --win-hp-bonus
        # is deliberately not passed (it is HP shaping).
        return STS2CurriculumRunEnv(
            acts=args.acts,
            card_obs=args.card_obs,
        )
    if args.env == "run":
        from sts2_rl.run_env import STS2RunEnv

        return STS2RunEnv(
            acts=args.acts,
            card_obs=args.card_obs,
            win_hp_bonus=args.win_hp_bonus,
        )
    return STS2FullCombatEnv(
        encounter=OVERGROWTH[args.encounter] if args.encounter else None,
        card_obs=args.card_obs,
        enemy_hp_reward_scale=args.enemy_hp_reward,
        win_hp_bonus=args.win_hp_bonus,
    )


def env_obs_schema(args: argparse.Namespace) -> int:
    """The schema version stamped into / checked against checkpoints —
    combat and run-scale envs version their layouts independently (run and
    column share one layout, hence one version)."""
    if args.env in ("run", "column"):
        from sts2_rl.run_env import RUN_OBS_SCHEMA_VERSION

        return RUN_OBS_SCHEMA_VERSION
    return OBS_SCHEMA_VERSION


def env_obs_segments(args: argparse.Namespace) -> list[tuple[str, int]]:
    """The named (segment, width) layout of this run's observation — what the
    entity model slices by. The run-scale envs report their trailing combat
    block as one opaque segment, so expand it into the combat layout here."""
    from sts2_rl.full_env import obs_segments

    combat = obs_segments(args.card_obs)
    if args.env in ("run", "column"):
        from sts2_rl.run_env import run_obs_segments

        return run_obs_segments(args.card_obs) + [
            (f"combat.{name}", width) for name, width in combat]
    return combat


def make_model(args: argparse.Namespace, obs_dim: int, n_actions: int) -> nn.Module:
    """Build the --arch-selected model for this run's env."""
    if args.arch == "entity":
        segments = env_obs_segments(args)
        seg_dim = sum(w for _, w in segments)
        if seg_dim != obs_dim:   # layout drift between env and segment map
            raise SystemExit(
                f"segment layout sums to {seg_dim} floats but the env emits "
                f"{obs_dim}; env_obs_segments is out of sync with the env.")
        return EntityActorCritic(segments, n_actions, hidden=tuple(args.hidden))
    return MaskedActorCritic(obs_dim, n_actions, hidden=tuple(args.hidden))


def check_checkpoint(ckpt: dict, args: argparse.Namespace,
                     obs_dim: int, n_actions: int) -> None:
    """Refuse a checkpoint that doesn't match this run's env/schema/model,
    with a clear message instead of a cryptic load_state_dict error."""
    ckpt_kind = ckpt.get("env_kind", "combat")
    # run and column share the observation/action layout, and moving a
    # checkpoint between them IS the curriculum plan's phase handoff.
    run_scale = {"run", "column"}
    if ckpt_kind != args.env and not ({ckpt_kind, args.env} <= run_scale):
        raise SystemExit(
            f"checkpoint was trained on the {ckpt_kind!r} env, "
            f"this run uses {args.env!r}; pick the matching --save/--resume or --fresh.")
    if ckpt_kind != args.env:
        print(f"Curriculum handoff: continuing a {ckpt_kind!r}-env checkpoint "
              f"on the {args.env!r} env.")
    if ckpt.get("obs_schema") != env_obs_schema(args):
        raise SystemExit(
            f"checkpoint obs schema {ckpt.get('obs_schema')} != current "
            f"{env_obs_schema(args)}; the observation layout changed — retrain.")
    ckpt_arch = ckpt.get("arch", "mlp")   # pre-stamp checkpoints are all MLP
    if ckpt_arch != args.arch:
        raise SystemExit(
            f"checkpoint arch {ckpt_arch!r} != this run's --arch {args.arch!r}; "
            f"there is no weight migration between architectures — pick the "
            f"matching --arch or start --fresh.")
    shape = (ckpt.get("obs_dim"), ckpt.get("n_actions"), tuple(ckpt.get("hidden", ())))
    want = (obs_dim, n_actions, tuple(args.hidden))
    if shape != want:
        raise SystemExit(
            f"checkpoint architecture {shape} != this run's {want} "
            f"(obs_dim, n_actions, hidden); can't resume — match --hidden or use --fresh.")


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    envs = [make_env(args) for _ in range(args.n_envs)]
    obs_dim = envs[0].observation_space.shape[0]
    n_actions = envs[0].action_space.n

    # Resolve which checkpoint (if any) to continue from: an explicit --resume
    # wins; otherwise re-running auto-continues the checkpoint at --save so a
    # bare `py train_torch.py` trains the same model further. --fresh forces a
    # new model even when one exists.
    resume_path = None
    if args.fresh:
        if args.resume:
            raise SystemExit("--fresh and --resume are mutually exclusive.")
    elif args.resume:
        resume_path = args.resume
    elif args.save and os.path.exists(args.save):
        resume_path = args.save
        print(f"Auto-resuming existing checkpoint {args.save} "
              f"(pass --fresh to start a new model).")

    agent = make_model(args, obs_dim, n_actions).to(device)
    optimizer = torch.optim.Adam(agent.parameters(), lr=args.lr, eps=1e-5)

    start_iter = 0
    if resume_path:
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        check_checkpoint(ckpt, args, obs_dim, n_actions)
        agent.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optim"])
        start_iter = ckpt.get("iteration", 0)
        print(f"Resumed from {resume_path} at iteration {start_iter}")

    # ── rollout buffers: [n_steps, n_envs, ...] ─────────────────────────────
    N, E = args.n_steps, args.n_envs
    obs_buf = torch.zeros((N, E, obs_dim), device=device)
    mask_buf = torch.zeros((N, E, n_actions), dtype=torch.bool, device=device)
    act_buf = torch.zeros((N, E), dtype=torch.long, device=device)
    logp_buf = torch.zeros((N, E), device=device)
    rew_buf = torch.zeros((N, E), device=device)
    done_buf = torch.zeros((N, E), device=device)
    val_buf = torch.zeros((N, E), device=device)

    def stack_masks() -> torch.Tensor:
        return torch.as_tensor(
            np.array([e.action_masks() for e in envs]), dtype=torch.bool, device=device)

    # initial state (distinct seed per env, then their RNG streams run on)
    next_obs = torch.as_tensor(
        np.array([e.reset(seed=args.seed + i)[0] for i, e in enumerate(envs)]),
        dtype=torch.float32, device=device)
    next_mask = stack_masks()
    next_done = torch.zeros(E, device=device)

    # episodic logging (raw env reward, not the training-time bootstrap fold-in)
    ep_ret_running = np.zeros(E, dtype=np.float64)
    ep_len_running = np.zeros(E, dtype=np.int64)
    ret_hist: deque[float] = deque(maxlen=100)
    len_hist: deque[int] = deque(maxlen=100)
    win_hist: deque[float] = deque(maxlen=100)

    batch_size = N * E
    mb_size = batch_size // args.minibatches
    n_iters = args.timesteps // batch_size
    global_step = 0
    t0 = time.time()

    for iteration in range(start_iter, start_iter + n_iters):
        # ── collect a rollout ───────────────────────────────────────────────
        for t in range(N):
            global_step += E
            obs_buf[t] = next_obs
            mask_buf[t] = next_mask
            done_buf[t] = next_done
            with torch.no_grad():
                action, logp, _, value = agent.get_action_and_value(next_obs, next_mask)
            val_buf[t] = value
            act_buf[t] = action
            logp_buf[t] = logp

            acts = action.cpu().numpy()
            new_obs = np.empty((E, obs_dim), np.float32)
            rewards = np.empty(E, np.float32)
            dones = np.empty(E, np.float32)
            for i, env in enumerate(envs):
                o, r, term, trunc, info = env.step(int(acts[i]))
                ep_ret_running[i] += r
                ep_len_running[i] += 1
                # Time-limit bootstrap: fold gamma*V(terminal obs) into the reward
                # and mark done, so GAE treats truncation correctly without a
                # separate terminal-value path (a natural termination bootstraps 0).
                if trunc and not term:
                    with torch.no_grad():
                        tv = agent.get_value(
                            torch.as_tensor(o, dtype=torch.float32, device=device).unsqueeze(0))
                    r = r + args.gamma * float(tv.item())
                done = term or trunc
                if done:
                    ret_hist.append(float(ep_ret_running[i]))
                    len_hist.append(int(ep_len_running[i]))
                    win_hist.append(1.0 if info.get("is_success") else 0.0)
                    ep_ret_running[i] = 0.0
                    ep_len_running[i] = 0
                    o, _ = env.reset()
                new_obs[i] = o
                rewards[i] = r
                dones[i] = float(done)
            rew_buf[t] = torch.as_tensor(rewards, device=device)
            next_obs = torch.as_tensor(new_obs, dtype=torch.float32, device=device)
            next_mask = stack_masks()
            next_done = torch.as_tensor(dones, device=device)

        # ── GAE ─────────────────────────────────────────────────────────────
        with torch.no_grad():
            next_value = agent.get_value(next_obs)
        advantages = torch.zeros_like(rew_buf)
        lastgae = torch.zeros(E, device=device)
        for t in reversed(range(N)):
            if t == N - 1:
                nonterminal = 1.0 - next_done
                nextval = next_value
            else:
                nonterminal = 1.0 - done_buf[t + 1]
                nextval = val_buf[t + 1]
            delta = rew_buf[t] + args.gamma * nextval * nonterminal - val_buf[t]
            lastgae = delta + args.gamma * args.gae_lambda * nonterminal * lastgae
            advantages[t] = lastgae
        returns = advantages + val_buf

        # ── flatten and update ──────────────────────────────────────────────
        b_obs = obs_buf.reshape(-1, obs_dim)
        b_mask = mask_buf.reshape(-1, n_actions)
        b_act = act_buf.reshape(-1)
        b_logp = logp_buf.reshape(-1)
        b_adv = advantages.reshape(-1)
        b_ret = returns.reshape(-1)
        b_val = val_buf.reshape(-1)

        idx = np.arange(batch_size)
        approx_kl = torch.tensor(0.0)
        clipfracs: list[float] = []
        for _ in range(args.epochs):
            np.random.shuffle(idx)
            for start in range(0, batch_size, mb_size):
                mb = idx[start:start + mb_size]
                _, newlogp, entropy, newval = agent.get_action_and_value(
                    b_obs[mb], b_mask[mb], b_act[mb])
                logratio = newlogp - b_logp[mb]
                ratio = logratio.exp()
                with torch.no_grad():
                    approx_kl = ((ratio - 1) - logratio).mean()
                    clipfracs.append(((ratio - 1.0).abs() > args.clip).float().mean().item())

                mb_adv = b_adv[mb]
                mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)

                pg_loss = torch.max(
                    -mb_adv * ratio,
                    -mb_adv * torch.clamp(ratio, 1 - args.clip, 1 + args.clip),
                ).mean()

                # clipped value loss
                v_unclipped = (newval - b_ret[mb]) ** 2
                v_clip = b_val[mb] + torch.clamp(newval - b_val[mb], -args.clip, args.clip)
                v_clipped = (v_clip - b_ret[mb]) ** 2
                v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()

                ent_loss = entropy.mean()
                loss = pg_loss - args.ent_coef * ent_loss + args.vf_coef * v_loss

                optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                optimizer.step()

            if args.target_kl is not None and approx_kl > args.target_kl:
                break

        # ── logging ─────────────────────────────────────────────────────────
        sps = int(global_step / (time.time() - t0))
        ret = np.mean(ret_hist) if ret_hist else float("nan")
        wr = np.mean(win_hist) if win_hist else float("nan")
        eplen = np.mean(len_hist) if len_hist else float("nan")
        print(
            f"iter {iteration:4d}  step {global_step:>9d}  sps {sps:>5d}  "
            f"ep_ret {ret:7.3f}  win {wr:5.2f}  ep_len {eplen:6.1f}  "
            f"pg {pg_loss.item():+.3f}  v {v_loss.item():.3f}  "
            f"ent {ent_loss.item():.3f}  kl {approx_kl.item():.4f}  "
            f"clipfrac {np.mean(clipfracs):.3f}",
            flush=True,
        )

        if args.save and (iteration + 1) % args.save_every == 0:
            save(agent, optimizer, iteration + 1, args)

    if args.save:
        save(agent, optimizer, start_iter + n_iters, args)
        print(f"Saved to {args.save}")

    for e in envs:
        e.close()


def save(agent: nn.Module, optimizer, iteration: int, args) -> None:
    import os
    d = os.path.dirname(args.save)
    if d:
        os.makedirs(d, exist_ok=True)
    torch.save(
        {
            "model": agent.state_dict(),
            "optim": optimizer.state_dict(),
            "iteration": iteration,
            "obs_dim": agent.obs_dim,
            "n_actions": agent.n_actions,
            "hidden": agent.hidden,
            "arch": args.arch,
            "obs_schema": env_obs_schema(args),
            "env_kind": args.env,
        },
        args.save,
    )


if __name__ == "__main__":
    main()
