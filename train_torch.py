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

Built for unattended multi-day runs: saves are atomic, each periodic save also
drops an iter-stamped snapshot (``--keep-snapshots``) and updates
``<stem>.best.pt`` (``--best-metric``) so a late policy collapse is
recoverable, and every iteration appends a row to ``<stem>.csv``. Checkpoints
carry ``global_step``, so a resume continues the step count, the CSV and the
env seeds rather than replaying the original run's opening episodes. Two
optimization guards go with that: ``--target-kl`` (on by default for the
run-scale envs) early-stops an epoch loop whose mean approx_kl says the update
moved the policy too far, and ``--anneal-lr`` decays the LR to 0 over the
invocation so an open-ended run doesn't sit at its warm-up LR forever.

This is the baseline loop from the plan: a plain MLP torso (``sts2_rl.models``)
trained with PPO. The one thing MaskablePPO did for us — applying
``env.action_masks()`` — we now do ourselves, at BOTH act-time and update-time,
so the ratio and entropy are computed over the same masked distribution the
agent acted under.

Single-file, hand-vectorized over ``--n-envs`` synchronous envs. Everything the
architecture plan cares about is swappable without touching this file: change
the torso in ``models.py``; change the observation in ``full_env.py``. The loop
only depends on the ``sts2_rl.vec_env`` interface and the model's three
methods.

Envs step in ``--n-workers`` processes — the default (-1, auto) uses 4
workers at training-scale env counts and the in-process serial path for
small runs (measured 2026-08-02: +57% sps combat / +42% column at 32 envs;
``sts2_rl.vec_env.resolve_n_workers`` has the numbers). The loop stays
lockstep-synchronous and produces identical rollouts either way.

Runs on CPU by default. For --arch mlp that is usually the fast choice: a
256x256 MLP over 8 Python-stepped envs is bottlenecked on env stepping and
per-step host<->device copies, not matmul. For --arch entity the balance
flips: the PPO update dominates, and on this machine (RTX 3070)
``--device cuda`` measured 1.5x the CPU sps at --n-envs 8 (2.4x at 16).
Measure ``sps`` before and after on new hardware rather than assuming.
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn

from sts2_rl import checkpoints, models
from sts2_rl.checkpoints import ModelSpec
from sts2_rl.tensor_obs import TensorObs
from sts2_rl.vec_env import EnvSpec, make_vec_env, resolve_n_workers

# --lr's default lives here rather than in add_argument so the flag can stay
# None when unset: on a resume that difference decides whether we keep the
# optimizer's restored LR or override it.
DEFAULT_LR = 6e-4

# --n-envs/--n-steps default here for the same reason: their product is the
# effective batch, and it lives outside the model, so a resume that silently
# reverts it keeps training the same weights at a different batch size — a
# config error that reads as a mysterious reward regression.
DEFAULT_N_ENVS = 64
DEFAULT_N_STEPS = 512

# One row per iteration in <stem>.csv. CSV, not TensorBoard, on purpose: zero
# dependencies, and a multi-day run's curve stays plottable from anything.
CSV_FIELDS = ["iter", "global_step", "wall_seconds", "sps", "ep_ret", "win",
              "ep_len", "pg", "v", "ent", "kl", "clipfrac", "lr",
              # Behavior metrics (run-scale envs only; NaN on --env combat):
              # mean energy left unspent per real end-turn, and the take rate
              # over resolved card-reward screens — both over the same
              # 100-episode window as ep_ret.
              "energy_unspent", "card_take",
              # v7 behavior counters (plan Task 7): per-episode means over the
              # same 100-episode window (run-scale envs only; NaN on combat).
              "upgrades", "removes", "elites", "potions_got", "potions_used",
              # v8 potion ledger (plan Task 2): USE classification + timing,
              # same per-episode-mean windowing as the v7 counters above.
              "potions_used_elite", "potions_used_boss", "potions_used_normal",
              "potions_expired", "potion_use_hp",
              # v8 relic reward (plan Task 3): per-episode mean, same
              # windowing as the v7 counters above.
              "relics",
              # v8 HP-economy (plan Task 1, plan Task 5 threading): mean HP
              # lost per episode -- a sloppiness gauge, tracked independent
              # of whether --hp-potential-scale shaping is on.
              "hp_lost"]


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
    ap.add_argument("--start-snapshots", default=None,
                    help="combat env only: path to a JSONL mid-run "
                         "start-state dataset (sts2_rl.snapshots), sampled "
                         "at every reset instead of the synthetic default "
                         "start (fresh basic deck, no relics, full HP, "
                         "empty belt). Mutually exclusive with --encounter "
                         "(the snapshot supplies the encounter too). "
                         "Recorded in the checkpoint's args on every save; "
                         "a resume without this flag drops back to "
                         "synthetic starts, and a resume WITH a different "
                         "path legitimately swaps datasets -- no refusal "
                         "logic on mismatch")
    ap.add_argument("--card-obs", choices=["hybrid", "features"], default="hybrid")
    ap.add_argument("--arch", choices=["mlp", "entity", "entset"], default="entset",
                    help="entset (default) = EntitySetActorCritic, the "
                         "v4-native arch (masked per-row embeddings over the "
                         "{f,i} pair); mlp = MaskedActorCritic (flat trunks "
                         "over concat(f, i), ids as plain numbers); entity = "
                         "EntityActorCritic (the same flat trunks, but the "
                         "v3-era per-segment embedding encoder -- against "
                         "the v4 obs it degenerates to the same raw "
                         "pass-through as mlp, see sts2_rl/models.py). "
                         "mlp/entity are refused against the current v4/v7 "
                         "envs (checkpoints.make_model): unnormalized "
                         "vocabulary ids would swamp the numeric features. "
                         "Checkpoints are arch-stamped — switching arch is a "
                         "full retrain")
    ap.add_argument("--enemy-hp-reward", type=float, default=0.0,
                    help="dense damage-dealt reward weight (0 = HP-delta + win only)")
    ap.add_argument("--win-hp-bonus", type=float, default=1.0,
                    help="combat env only: terminal win bonus scaled by final HP fraction: "
                         "win reward is reward_win + win_hp_bonus*(hp/max_hp), so clean wins "
                         "beat sloppy ones (0 = flat win bonus, the old behavior). The "
                         "run-scale envs use the floor-only reward (no HP shaping)")
    ap.add_argument("--branch-prob", type=float, default=0.0,
                    help="column env only: probability that an episode uses a "
                         "real branching StandardMap instead of a single column "
                         "(0.0 = pure column, 1.0 = pure branching). Annealing "
                         "this across stages eases the column→run transition")
    ap.add_argument("--ascension", type=int, default=0,
                    help="run/column envs only: the ascension level new runs "
                         "start at (0 = no ascension, the old behavior). "
                         "Stamped into the checkpoint alongside env_kind; "
                         "unlike env_kind/schema/arch a resume WARNS rather "
                         "than refuses on a mismatch -- v7 deliberately "
                         "resumes training across ascensions.")
    # v7 reward/curriculum knobs (plan Task 7; run/column envs only, all
    # default OFF so a plain invocation trains exactly as before).
    ap.add_argument("--floor-rewards", type=float, nargs=3, default=None,
                    metavar=("ACT1", "ACT2", "ACT3"),
                    help="per-floor reward by act (e.g. 1.0 1.5 2.0), replacing "
                         "the flat +1/floor. Unset keeps the flat reward")
    ap.add_argument("--reward-win", type=float, default=None,
                    help="terminal win bonus for the run-scale envs "
                         "(default: the env's own 3.0)")
    ap.add_argument("--reward-upgrade", type=float, default=0.0,
                    help="reward per permanent card upgrade gained")
    ap.add_argument("--reward-remove", type=float, default=0.0,
                    help="reward per card removed from the deck")
    ap.add_argument("--reward-elite", type=float, default=0.0,
                    help="reward per elite fight won")
    ap.add_argument("--reward-relic", type=float, default=0.0,
                    help="reward per relic gained (v8 plan Task 3; the "
                         "starting relic never counts)")
    ap.add_argument("--rest-heal-mask-above", type=float, default=None,
                    help="v8 plan Task 4: at a rest site, above this hp/max_hp "
                         "ratio, mask out REST_HEAL if another rest action is "
                         "legal (forces upgrade-path data instead of always "
                         "topping off). Unset = no masking (default)")
    ap.add_argument("--hp-potential-scale", type=float, default=0.0,
                    help="v8 plan Task 1: concave HP-potential shaping weight "
                         "(0 = off, the old behavior). knee/low_share stay at "
                         "the env's own defaults -- not exposed as flags")
    ap.add_argument("--potion-potential-scale", type=float, default=0.0,
                    help="v8 plan Task 2: potion-ledger shaping weight -- "
                         "+/-scale per potion gained/lost off the belt-count "
                         "delta (0 = off, the old behavior)")
    ap.add_argument("--deck-random-prob", type=float, default=0.0,
                    help="probability an episode starts with a randomized deck "
                         "(card-exposure domain randomization; 0.0 = never)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cpu",
                    help="cpu (default; fastest for --arch mlp), cuda "
                         "(measured faster for --arch entity -- see the "
                         "module docstring), or auto")
    ap.add_argument("--save", default=None,
                    help="checkpoint path (default: runs/sts2_torch.pt for "
                         "--env combat, runs/sts2_run_torch.pt for --env run, "
                         "runs/sts2_column_torch.pt for --env column)")
    ap.add_argument("--resume", default=None,
                    help="continue from this checkpoint (default: auto-resume --save if it exists)")
    ap.add_argument("--fresh", action="store_true",
                    help="start a new model even if a checkpoint exists at --save")
    ap.add_argument("--warm-start", default=None,
                    help="cross-kind partial load (Task 6b, sts2_rl.checkpoints."
                         "warm_start_agent): build a FRESH model for this run's "
                         "--env/--arch and transfer whatever structurally "
                         "matches from this checkpoint -- which may be a "
                         "DIFFERENT env kind (run <-> combat), unlike --resume. "
                         "Fresh optimizer/iteration/global_step either way -- "
                         "a warm-start is a new run with warm weights, not a "
                         "resume. Requires --arch entset on both sides. "
                         "Mutually exclusive with --resume/--fresh.")
    ap.add_argument("--save-every", type=int, default=10, help="iterations between checkpoints")
    ap.add_argument("--keep-snapshots", type=int, default=5,
                    help="how many iter-stamped snapshots (<stem>.iter000123.pt) "
                         "to keep alongside the live checkpoint, so a late "
                         "policy collapse can be rolled back (0 = none)")
    ap.add_argument("--best-metric", choices=["win", "ep_ret", "none"], default=None,
                    help="which 100-episode statistic <stem>.best.pt tracks "
                         "(default: win for --env combat/run, ep_ret for the "
                         "floor-only column curriculum). This is the exploring "
                         "policy's own metric, not a greedy eval — treat it as "
                         "a rollback candidate, not a leaderboard")
    # rollout / PPO
    ap.add_argument("--n-envs", type=int, default=None,
                    help=f"parallel envs (default: {DEFAULT_N_ENVS}). Left as "
                         f"None when unset so a resume keeps the checkpoint's "
                         f"rollout geometry instead of silently reverting it")
    ap.add_argument("--n-workers", type=int, default=-1,
                    help="processes to step envs in (default -1: auto — 4 "
                         "workers at 16+ envs, serial below; measured "
                         "2026-08-02 at +57%%/+42%% sps combat/column at 32 "
                         "envs). 0 forces in-process. The layout is a "
                         "runtime detail: seeding, rollouts and checkpoints "
                         "are identical at any worker count")
    ap.add_argument("--n-steps", type=int, default=None,
                    help=f"rollout length per env (default: {DEFAULT_N_STEPS}); "
                         f"None when unset, like --n-envs")
    ap.add_argument("--lr", type=float, default=None,
                    help=f"learning rate (default: {DEFAULT_LR:g}). Left as None "
                         f"when unset so a resume can tell 'use the checkpoint's "
                         f"restored LR' from an explicit override")
    ap.add_argument("--gamma", type=float, default=None,
                    help="discount (default: 0.99 for --env combat, 0.999 for "
                         "the run-scale envs — a full run is 1000+ steps, and "
                         "floor-only reward needs deaths to stay visible from "
                         "the HP loss that caused them)")
    ap.add_argument("--gae-lambda", type=float, default=0.95)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--minibatches", type=int, default=16)
    ap.add_argument("--ent-coef", type=float, default=0.01)
    ap.add_argument("--ent-coef-final", type=float, default=None,
                    help="anneal the entropy bonus linearly from --ent-coef to "
                         "this over the run (default: equal to --ent-coef, "
                         "i.e. constant)")
    ap.add_argument("--vf-coef", type=float, default=0.5)
    ap.add_argument("--max-grad-norm", type=float, default=0.5)
    ap.add_argument("--anneal-lr", action="store_true",
                    help="linearly decay the learning rate from --lr to 0 over "
                         "this invocation's iterations (off by default). A "
                         "resume RESTARTS the schedule over the new "
                         "--timesteps budget, and ignores the LR restored from "
                         "the checkpoint — the sane behavior for open-ended "
                         "resume-based training")
    ap.add_argument("--target-kl", type=float, default=None,
                    help="early-stop the epoch loop when the running mean of "
                         "the current epoch's approx_kl exceeds this, checked "
                         "after every minibatch (default: 0.02 for --env "
                         "run/column, off for --env combat; pass 0 to turn it "
                         "off explicitly)")
    ap.add_argument("--critic-warmup", type=int, default=0,
                    help="train the VALUE HEAD ONLY for this many iterations "
                         "at the start of this invocation, leaving the policy "
                         "bit-identical. Use it when resuming after a change "
                         "that moves the return distribution (a new reward "
                         "term, an env rule like a per-act heal): the critic "
                         "is stale, its advantages are mis-signed, and a "
                         "full-LR resume spends them wrecking a good policy")
    ap.add_argument("--zero-segments", nargs="+", default=[], metavar="SEGMENT",
                    help="hold the first-layer columns fed by these obs "
                         "segments at zero in BOTH heads, so the model behaves "
                         "as if the segment were absent (--arch entity only). "
                         "Diagnostic: a segment spliced in by a checkpoint "
                         "migration starts at exactly zero, and zeroing it "
                         "again reproduces the pre-migration model exactly, "
                         "which isolates whether that segment is what "
                         "destabilised a resume")
    ap.add_argument("--shared-encoder", action="store_true",
                    help="--arch entset only: build ONE _EntsetEncoder "
                         "instance shared by the actor and critic instead "
                         "of two independent ones (R10 A/B) -- the two "
                         "trunks/heads stay separate either way. Checkpoints "
                         "stamp this and refuse a mismatched reload; there "
                         "is no weight migration between the two arms")
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
    if args.target_kl is None:
        # The run-scale envs are long-horizon and high-variance, where one
        # destructive update costs hours to recover from; measured KL on a
        # healthy column run is ~0.01, comfortably under this. --env combat
        # keeps the old off-by-default behavior.
        args.target_kl = None if args.env == "combat" else 0.02
    elif args.target_kl <= 0:
        args.target_kl = None                # explicit opt-out
    if args.ent_coef_final is None:
        args.ent_coef_final = args.ent_coef
    if args.best_metric is None:
        # The column curriculum's reward IS floors reached, and its win rate
        # (a full three-act clear) stays 0 for most of training — ep_ret is
        # the only statistic that moves there.
        args.best_metric = "ep_ret" if args.env == "column" else "win"
    if args.env != "combat" and args.encounter:
        raise SystemExit("--encounter applies to --env combat only.")
    if args.env != "combat" and args.start_snapshots:
        raise SystemExit("--start-snapshots applies to --env combat only.")
    if args.encounter and args.start_snapshots:
        raise SystemExit(
            "--encounter and --start-snapshots are mutually exclusive "
            "(a snapshot supplies the encounter too).")
    if args.env == "combat" and args.acts:
        raise SystemExit("--acts applies to the run-scale envs only.")
    # NOTE: --ascension is deliberately NOT rejected for --env combat. v7
    # Task 5 rejected it here because STS2FullCombatEnv didn't take the
    # kwarg yet; v7 Task 10 added it (gimmick probes fight at the stage's
    # ascension) and relaxed eval.py's guard, but left this one stale. The
    # v8 curriculum trains combat stages at asc 10 directly, so this guard
    # must go too -- EnvSpec.ascension already threads to all three env
    # kinds (see vec_env.EnvSpec's own comment).
    if args.env == "combat" and (
            args.floor_rewards is not None or args.reward_win is not None
            or args.reward_upgrade or args.reward_remove or args.reward_elite
            or args.reward_relic or args.rest_heal_mask_above is not None
            or args.hp_potential_scale or args.potion_potential_scale
            or args.deck_random_prob):
        raise SystemExit(
            "--floor-rewards/--reward-win/--reward-upgrade/--reward-remove/"
            "--reward-elite/--reward-relic/--rest-heal-mask-above/"
            "--hp-potential-scale/--potion-potential-scale/"
            "--deck-random-prob apply to the run-scale envs only.")
    if args.branch_prob and args.env != "column":
        raise SystemExit(
            f"--branch-prob applies to --env column only (got --env {args.env})")
    if args.warm_start and (args.resume or args.fresh):
        raise SystemExit(
            "--warm-start is mutually exclusive with --resume/--fresh: it is "
            "already its own way of starting a run (fresh optimizer/"
            "iteration, weights transferred from --warm-start's checkpoint).")
    if args.warm_start and args.arch != "entset":
        raise SystemExit(
            f"--warm-start requires --arch entset (got --arch {args.arch!r}); "
            f"the mlp/entity archs have fixed-width heads with no cross-kind "
            f"structural correspondence to transfer.")
    return args


def anneal_fraction(iteration: int, start_iter: int, n_iters: int) -> float:
    """How far through THIS invocation's iterations we are: 0.0 on the first,
    ``(n_iters - 1) / n_iters`` on the last.

    Deliberately counted from ``start_iter`` rather than from 0, so a resumed
    run runs a fresh schedule over its own ``--timesteps`` budget instead of
    inheriting a decayed tail from the checkpoint's original run.
    """
    return (iteration - start_iter) / n_iters if n_iters > 0 else 0.0


def anneal(start_value: float, end_value: float, fraction: float) -> float:
    """Linear interpolation from ``start_value`` to ``end_value``."""
    return start_value + (end_value - start_value) * fraction


def kl_exceeded(kls: list[float], epoch_start: int, target_kl: float | None,
                min_samples: int = 2) -> bool:
    """Should the epoch loop stop? True when the MEAN of the current epoch's
    minibatch KLs SO FAR (those from ``epoch_start`` on) exceeds ``target_kl``.

    The mean, not the last minibatch's value: with 8 minibatches the tail
    value swings enough to both abort a perfectly healthy update and wave
    through an epoch that really did move the policy too far.

    Scored after EVERY minibatch, not only at the epoch boundary. A boundary-
    only check bounds nothing: the obs-v4 resume put a full epoch through at
    mean KL 0.13 — 30x a healthy iteration and 6x the target — and that single
    epoch cost the policy 4 reward points it never recovered. ``min_samples``
    keeps the mean-not-last-value rationale intact by refusing to fire on one
    noisy minibatch; callers with fewer minibatches than that must lower it or
    the guard never fires at all.
    """
    if target_kl is None:
        return False
    seen = kls[epoch_start:]
    if len(seen) < max(1, min_samples):
        return False
    return float(np.mean(seen)) > target_kl


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


def env_spec(args: argparse.Namespace) -> EnvSpec:
    """This run's env flags, in the picklable form workers are built from."""
    return EnvSpec(
        kind=args.env,
        acts=tuple(args.acts) if args.acts else None,
        card_obs=args.card_obs,
        encounter=args.encounter,
        enemy_hp_reward=args.enemy_hp_reward,
        win_hp_bonus=args.win_hp_bonus,
        branch_prob=args.branch_prob,
        start_snapshots=getattr(args, "start_snapshots", None),
        ascension=getattr(args, "ascension", 0),
        floor_rewards_by_act=(tuple(args.floor_rewards)
                              if getattr(args, "floor_rewards", None) is not None
                              else None),
        reward_win_run=getattr(args, "reward_win", None),
        reward_upgrade=getattr(args, "reward_upgrade", 0.0),
        reward_remove=getattr(args, "reward_remove", 0.0),
        reward_elite=getattr(args, "reward_elite", 0.0),
        reward_relic=getattr(args, "reward_relic", 0.0),
        rest_heal_mask_above=getattr(args, "rest_heal_mask_above", None),
        hp_potential_scale=getattr(args, "hp_potential_scale", 0.0),
        potion_potential_scale=getattr(args, "potion_potential_scale", 0.0),
        deck_random_prob=getattr(args, "deck_random_prob", 0.0),
    )


def model_spec(args: argparse.Namespace) -> ModelSpec:
    """This run's env/arch/hidden triple — the shared construction key that
    ``sts2_rl.checkpoints`` (and therefore ``eval.py``) builds models from."""
    return ModelSpec(
        env_kind=args.env,
        card_obs=args.card_obs,
        arch=args.arch,
        hidden=tuple(args.hidden),
        # getattr, not args.shared_encoder: several test fixtures build a
        # bare argparse.Namespace() by hand without every CLI flag (this
        # file's own real parse_args() always sets it via the --shared-
        # encoder store_true default of False, so this only matters off the
        # real CLI path).
        shared_encoder=getattr(args, "shared_encoder", False),
    )


def env_obs_schema(args: argparse.Namespace) -> int:
    return checkpoints.obs_schema_version(model_spec(args))


def env_obs_segments(args: argparse.Namespace) -> list[tuple[str, int]]:
    return checkpoints.model_obs_segments(model_spec(args))


def segment_spans(agent: nn.Module, names: list[str]) -> list[tuple[int, int]]:
    """First-layer column spans fed by the named obs segments.

    Raises on an unknown name rather than silently masking nothing — a typo'd
    segment would otherwise make a null experiment look like a real result.
    """
    if not names:
        return []
    if getattr(agent, "arch", None) == "entset":
        # T6 brief §4.4's explicit escape hatch: entset's encoder masked-
        # sum-pools per-row projections rather than exposing a flat first-
        # layer column range per segment, so the mlp/entity column-zeroing
        # trick (apply_zero_segments below) doesn't have a column range to
        # zero. Re-expressing the ablation as zeroing the segment's pooled
        # CONTRIBUTION inside the encoder's forward is real future work, not
        # attempted here — a silently-no-op flag would be worse than this
        # refusal.
        raise SystemExit(
            "--zero-segments is not implemented for --arch entset: its "
            "encoder pools per-row embeddings rather than exposing a flat "
            "first-layer column range per segment, so the mlp/entity "
            "column-zeroing trick doesn't apply. Use --arch entity for this "
            "diagnostic, or omit --zero-segments.")
    if not hasattr(agent, "actor_encoder"):
        raise SystemExit("--zero-segments needs --arch entity (no segment "
                         "encoder to take column spans from)")
    spans = agent.actor_encoder.out_spans
    unknown = [n for n in names if n not in spans]
    if unknown:
        raise SystemExit(f"--zero-segments: unknown segment(s) {unknown}. "
                         f"Known: {sorted(spans)}")
    return [spans[n] for n in names]


def apply_zero_segments(agent: nn.Module, spans: list[tuple[int, int]]) -> None:
    """Re-zero the masked columns in both trunks' first Linear.

    Called after every optimizer.step() rather than via a gradient hook:
    Adam carries momentum, so a column with a zero gradient still drifts if
    its exp_avg is non-zero. Overwriting the weight is the only version of
    this that is actually airtight.
    """
    with torch.no_grad():
        for start, stop in spans:
            agent.actor[0].weight[:, start:stop].zero_()
            agent.critic[0].weight[:, start:stop].zero_()


def make_model(args: argparse.Namespace, obs_dim: int, n_actions: int) -> nn.Module:
    """Build the --arch-selected model for this run's env."""
    return checkpoints.make_model(model_spec(args), obs_dim, n_actions)


def check_checkpoint(ckpt: dict, args: argparse.Namespace,
                     obs_dim: int, n_actions: int) -> None:
    """Refuse a checkpoint that doesn't match this run's env/schema/model,
    with a clear message instead of a cryptic load_state_dict error."""
    checkpoints.check_checkpoint(ckpt, model_spec(args), obs_dim, n_actions)


def resolve_rollout_geometry(args, ckpt: dict | None) -> tuple[int, int]:
    """(n_envs, n_steps), resolved explicit flag > checkpoint > default.

    Each field falls back independently, so a pre-hardening checkpoint that
    records neither still resumes at the defaults.
    """
    ckpt = ckpt or {}
    n_envs = args.n_envs if args.n_envs is not None else ckpt.get("n_envs", DEFAULT_N_ENVS)
    n_steps = args.n_steps if args.n_steps is not None else ckpt.get("n_steps", DEFAULT_N_STEPS)
    return n_envs, n_steps


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # Resolve which checkpoint (if any) to continue from: an explicit --resume
    # wins; otherwise re-running auto-continues the checkpoint at --save so a
    # bare `py train_torch.py` trains the same model further. --fresh forces a
    # new model even when one exists. --warm-start (parse_args already refused
    # combining it with --resume/--fresh) is its own path below -- it never
    # sets resume_path, so the rollout geometry and (later) the model start
    # fresh/explicit rather than inherited from the warm-start source. This
    # runs before the envs are built because a --resume checkpoint carries
    # the rollout geometry they are sized from.
    resume_path = None
    if args.fresh:
        if args.resume:
            raise SystemExit("--fresh and --resume are mutually exclusive.")
    elif args.resume:
        resume_path = args.resume
    elif not args.warm_start and args.save and os.path.exists(args.save):
        resume_path = args.save
        print(f"Auto-resuming existing checkpoint {args.save} "
              f"(pass --fresh to start a new model).")

    ckpt = (torch.load(resume_path, map_location=device, weights_only=False)
            if resume_path else None)
    args.n_envs, args.n_steps = resolve_rollout_geometry(args, ckpt)

    n_workers = resolve_n_workers(args.n_envs, args.n_workers)
    envs = make_vec_env(env_spec(args), args.n_envs, n_workers)
    print(f"{args.n_envs} envs x {args.n_steps} steps "
          f"(batch {args.n_envs * args.n_steps}) across "
          + (f"{envs.n_workers} worker processes" if envs.n_workers
             else "the in-process serial path"), flush=True)
    obs_dim = envs.obs_dim
    n_actions = envs.n_actions

    agent = make_model(args, obs_dim, n_actions).to(device)
    base_lr = DEFAULT_LR if args.lr is None else args.lr
    optimizer = torch.optim.Adam(agent.parameters(), lr=base_lr, eps=1e-5)

    start_iter = 0
    start_step = 0
    best_score = -math.inf
    if resume_path:
        check_checkpoint(ckpt, args, obs_dim, n_actions)
        checkpoints.check_ascension(ckpt, args.ascension)
        agent.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optim"])
        start_iter = ckpt.get("iteration", 0)
        # Pre-hardening checkpoints carry neither field; 0 / -inf just means
        # "step count restarts here" and "no best on record yet".
        start_step = ckpt.get("global_step", 0)
        best_score = ckpt.get("best_score", -math.inf)
        # load_state_dict restores the *saved* LR, so an explicit --lr on a
        # resume would otherwise be silently ignored.
        if args.lr is not None:
            for group in optimizer.param_groups:
                group["lr"] = args.lr
            print(f"Overriding the checkpoint's learning rate with --lr {args.lr:g}")
        print(f"Resumed from {resume_path} at iteration {start_iter} "
              f"(step {start_step})")
    elif args.warm_start:
        # Deliberately NOT check_checkpoint/check_ascension -- those refuse
        # exactly the cross-kind handoff --warm-start exists for. Fresh
        # optimizer/start_iter/start_step/best_score (already the defaults
        # set above): a warm-start is a new run with warm weights, not a
        # resume (T6b brief). parse_args already refused --arch != entset.
        warm_ckpt = torch.load(args.warm_start, map_location=device, weights_only=False)
        checkpoints.warm_start_agent(agent, warm_ckpt, model_spec(args))

    # After the resume, so this masks the loaded weights rather than the fresh
    # ones the load would overwrite.
    zero_spans = segment_spans(agent, args.zero_segments)
    if zero_spans:
        apply_zero_segments(agent, zero_spans)
        masked = sum(stop - start for start, stop in zero_spans)
        print(f"Holding {masked} first-layer columns at zero for "
              f"{', '.join(args.zero_segments)} "
              f"({100 * masked / agent.actor[0].weight.shape[1]:.1f}% of the "
              f"trunk's input)")

    # ── rollout buffers: [n_steps, n_envs, ...] ─────────────────────────────
    N, E = args.n_steps, args.n_envs
    f_dim, i_dim = obs_dim
    obs_buf = TensorObs(
        torch.zeros((N, E, f_dim), device=device),
        torch.zeros((N, E, i_dim), dtype=torch.long, device=device),
    )
    mask_buf = torch.zeros((N, E, n_actions), dtype=torch.bool, device=device)
    act_buf = torch.zeros((N, E), dtype=torch.long, device=device)
    logp_buf = torch.zeros((N, E), device=device)
    rew_buf = torch.zeros((N, E), device=device)
    done_buf = torch.zeros((N, E), device=device)
    val_buf = torch.zeros((N, E), device=device)

    # Initial state: distinct seed per env, then their RNG streams run on.
    # start_iter is folded in so a resumed run opens on fresh episodes instead
    # of replaying the original run's first draws. The seed is the env's GLOBAL
    # index, so the worker layout can't shift which stream an env gets.
    reset_obs, reset_mask = envs.reset(
        [args.seed + start_iter * E + i for i in range(E)])
    next_obs = reset_obs.to(device)
    next_mask = torch.as_tensor(reset_mask, dtype=torch.bool, device=device)
    next_done = torch.zeros(E, device=device)

    # episodic logging (raw env reward, not the training-time bootstrap fold-in)
    ep_ret_running = np.zeros(E, dtype=np.float64)
    ep_len_running = np.zeros(E, dtype=np.int64)
    ret_hist: deque[float] = deque(maxlen=100)
    len_hist: deque[int] = deque(maxlen=100)
    win_hist: deque[float] = deque(maxlen=100)
    # Behavior metrics (StepBatch.metrics, EP_METRIC_KEYS order). Kept as
    # per-episode (count, sum) pairs so the window average weights by events,
    # not episodes — an episode with one card offer shouldn't count as much
    # as one with twelve.
    endturn_hist: deque[tuple[float, float]] = deque(maxlen=100)   # (end_turns, energy_unspent)
    cardrew_hist: deque[tuple[float, float]] = deque(maxlen=100)   # (offers, takes)
    # v7 counters (EP_METRIC_KEYS[4:9]): plain per-episode counts, so the
    # window statistic is a straight mean per episode.
    v7_hist: deque[tuple[float, ...]] = deque(maxlen=100)          # (upgrades, removes, elites, potions_got, potions_used)
    # v8 potion ledger (plan Task 2, EP_METRIC_KEYS[9:14]): same
    # per-episode-count windowing as v7_hist.
    v8_potion_hist: deque[tuple[float, ...]] = deque(maxlen=100)   # (used_elite, used_boss, used_normal, expired, use_hp)
    # v8 relic reward (plan Task 3, EP_METRIC_KEYS[14]): same per-episode-count
    # windowing as v7_hist/v8_potion_hist.
    v8_relic_hist: deque[float] = deque(maxlen=100)
    # v8 HP-economy (plan Task 1, EP_METRIC_KEYS[15]): same per-episode-count
    # windowing as v8_relic_hist.
    v8_hplost_hist: deque[float] = deque(maxlen=100)

    batch_size = N * E
    mb_size = batch_size // args.minibatches
    n_iters = args.timesteps // batch_size
    global_step = start_step
    t0 = time.time()

    # Workers are daemons, but close them explicitly so a Ctrl-C or a
    # crash mid-run tears them down now rather than at interpreter exit.
    try:
        for iteration in range(start_iter, start_iter + n_iters):
            # ── schedules ───────────────────────────────────────────────────────
            # Both run over this invocation's iterations (see anneal_fraction).
            # The LR has to be re-set every iteration, and here rather than at
            # resume time: optimizer.load_state_dict above restored the
            # checkpoint's LR into the param groups.
            frac = anneal_fraction(iteration, start_iter, n_iters)
            if args.anneal_lr:
                for group in optimizer.param_groups:
                    group["lr"] = anneal(base_lr, 0.0, frac)
            ent_coef = anneal(args.ent_coef, args.ent_coef_final, frac)

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

                # The vec env auto-resets finished episodes, so `batch.obs` is
                # already the observation to act from next step.
                batch = envs.step(action.cpu().numpy())
                ep_ret_running += batch.rewards          # raw reward, pre-bootstrap
                ep_len_running += 1

                rewards = batch.rewards.astype(np.float32).copy()
                # Time-limit bootstrap: fold gamma*V(terminal obs) into the reward
                # and mark done, so GAE treats truncation correctly without a
                # separate terminal-value path (a natural termination bootstraps 0).
                # One forward per truncation rather than a batched one: truncations
                # are rare, and this keeps the arithmetic bit-identical to the
                # serial path.
                for i, final_obs in batch.final_obs.items():
                    with torch.no_grad():
                        tv = agent.get_value(final_obs.to(device)[None])
                    rewards[i] += args.gamma * float(tv.item())

                dones = batch.terminated | batch.truncated
                for i in np.flatnonzero(dones):
                    ret_hist.append(float(ep_ret_running[i]))
                    len_hist.append(int(ep_len_running[i]))
                    win_hist.append(1.0 if batch.successes[i] else 0.0)
                    m = batch.metrics[i]
                    if not math.isnan(m[0]):
                        endturn_hist.append((float(m[0]), float(m[1])))
                        cardrew_hist.append((float(m[2]), float(m[3])))
                    if not math.isnan(m[4]):
                        v7_hist.append(tuple(float(x) for x in m[4:9]))
                    if not math.isnan(m[9]):
                        v8_potion_hist.append(tuple(float(x) for x in m[9:14]))
                    if not math.isnan(m[14]):
                        v8_relic_hist.append(float(m[14]))
                    if not math.isnan(m[15]):
                        v8_hplost_hist.append(float(m[15]))
                    ep_ret_running[i] = 0.0
                    ep_len_running[i] = 0

                rew_buf[t] = torch.as_tensor(rewards, device=device)
                next_obs = batch.obs.to(device)
                next_mask = torch.as_tensor(batch.masks, dtype=torch.bool, device=device)
                next_done = torch.as_tensor(dones.astype(np.float32), device=device)

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
            kls: list[float] = []
            clipfracs: list[float] = []
            # A stale critic's advantages are mis-signed, so spend the first
            # --critic-warmup iterations fitting the value head alone. The
            # actor's parameters are disjoint from the critic's (separate
            # trunks, and separate encoders for --arch entity), so dropping
            # the policy and entropy terms leaves the actor out of the graph
            # entirely: zero_grad() sets its grads to None and Adam skips it,
            # momentum included. The policy comes out bit-identical.
            critic_only = iteration < start_iter + args.critic_warmup
            stop_epochs = False
            for _ in range(args.epochs):
                if stop_epochs:
                    break
                epoch_start = len(kls)
                np.random.shuffle(idx)
                for start in range(0, batch_size, mb_size):
                    mb = idx[start:start + mb_size]
                    _, newlogp, entropy, newval = agent.get_action_and_value(
                        b_obs[mb], b_mask[mb], b_act[mb])
                    logratio = newlogp - b_logp[mb]
                    ratio = logratio.exp()
                    with torch.no_grad():
                        kls.append(float(((ratio - 1) - logratio).mean()))
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
                    if critic_only:
                        loss = args.vf_coef * v_loss
                    else:
                        loss = pg_loss - ent_coef * ent_loss + args.vf_coef * v_loss

                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(agent.parameters(), args.max_grad_norm)
                    optimizer.step()
                    if zero_spans:
                        apply_zero_segments(agent, zero_spans)

                    # Checked here rather than at the epoch boundary so a
                    # destructive update costs a minibatch or two, not a whole
                    # epoch. During the warm-up the policy cannot move, so the
                    # KLs are 0 and this never fires.
                    if kl_exceeded(kls, epoch_start, args.target_kl,
                                   min_samples=min(2, args.minibatches)):
                        stop_epochs = True
                        break
            approx_kl = float(np.mean(kls)) if kls else float("nan")

            # ── logging ─────────────────────────────────────────────────────────
            # sps measures THIS process's throughput, so a resume doesn't report
            # the whole history's steps over this run's seconds.
            elapsed = time.time() - t0
            sps = int((global_step - start_step) / elapsed)
            ret = np.mean(ret_hist) if ret_hist else float("nan")
            wr = np.mean(win_hist) if win_hist else float("nan")
            eplen = np.mean(len_hist) if len_hist else float("nan")
            n_endturns = sum(c for c, _ in endturn_hist)
            energy_unspent = (sum(s for _, s in endturn_hist) / n_endturns
                              if n_endturns else float("nan"))
            n_offers = sum(c for c, _ in cardrew_hist)
            card_take = (sum(s for _, s in cardrew_hist) / n_offers
                         if n_offers else float("nan"))
            v7_means = (np.mean(np.asarray(v7_hist, dtype=np.float64), axis=0)
                        if v7_hist else [float("nan")] * 5)
            v8_potion_means = (
                np.mean(np.asarray(v8_potion_hist, dtype=np.float64), axis=0)
                if v8_potion_hist else [float("nan")] * 5)
            v8_relic_mean = (
                float(np.mean(v8_relic_hist)) if v8_relic_hist else float("nan"))
            v8_hplost_mean = (
                float(np.mean(v8_hplost_hist)) if v8_hplost_hist else float("nan"))
            lr = optimizer.param_groups[0]["lr"]
            print(
                f"iter {iteration:4d}  step {global_step:>9d}  sps {sps:>5d}  "
                f"ep_ret {ret:7.3f}  win {wr:5.2f}  ep_len {eplen:6.1f}  "
                f"pg {pg_loss.item():+.3f}  v {v_loss.item():.3f}  "
                f"ent {ent_loss.item():.3f}  kl {approx_kl:.4f}  "
                f"clipfrac {np.mean(clipfracs):.3f}  "
                f"e_unspent {energy_unspent:4.2f}  take {card_take:4.2f}"
                # pg/ent are still reported during the warm-up (they say how
                # stale the advantages are) but were not applied — mark it so
                # a flat ep_ret here doesn't read as a stalled run.
                + ("  [critic-warmup]" if critic_only else ""),
                flush=True,
            )
            if args.save:
                append_csv_row(csv_path(args.save), dict(
                    iter=iteration, global_step=global_step,
                    wall_seconds=round(elapsed, 3), sps=sps,
                    ep_ret=ret, win=wr, ep_len=eplen,
                    pg=pg_loss.item(), v=v_loss.item(), ent=ent_loss.item(),
                    kl=approx_kl, clipfrac=float(np.mean(clipfracs)), lr=lr,
                    energy_unspent=energy_unspent, card_take=card_take,
                    upgrades=float(v7_means[0]), removes=float(v7_means[1]),
                    elites=float(v7_means[2]), potions_got=float(v7_means[3]),
                    potions_used=float(v7_means[4]),
                    potions_used_elite=float(v8_potion_means[0]),
                    potions_used_boss=float(v8_potion_means[1]),
                    potions_used_normal=float(v8_potion_means[2]),
                    potions_expired=float(v8_potion_means[3]),
                    potion_use_hp=float(v8_potion_means[4]),
                    relics=v8_relic_mean,
                    hp_lost=v8_hplost_mean,
                ))

            # ── checkpointing ───────────────────────────────────────────────────
            if args.save and (iteration + 1) % args.save_every == 0:
                score = {"win": wr, "ep_ret": ret}.get(args.best_metric, float("nan"))
                if not math.isnan(score) and score > best_score:
                    best_score = float(score)
                    new_best = True
                else:
                    new_best = False
                payload = checkpoint_payload(
                    agent, optimizer, iteration + 1, args, global_step, best_score)
                atomic_save(payload, args.save)
                if args.keep_snapshots:
                    atomic_save(payload, snapshot_path(args.save, iteration + 1))
                    rotate_snapshots(args.save, args.keep_snapshots)
                if new_best:
                    atomic_save(payload, best_path(args.save))

        if args.save:
            save(agent, optimizer, start_iter + n_iters, args,
                 global_step=global_step, best_score=best_score)
            print(f"Saved to {args.save}")
    finally:
        envs.close()


def _stem(save_path: str) -> str:
    """``runs/x.pt`` -> ``runs/x`` — the prefix every sidecar file hangs off."""
    return save_path[:-3] if save_path.endswith(".pt") else save_path


def snapshot_path(save_path: str, iteration: int) -> str:
    """Zero-padded so snapshots sort lexicographically by iteration."""
    return f"{_stem(save_path)}.iter{iteration:06d}.pt"


def best_path(save_path: str) -> str:
    return f"{_stem(save_path)}.best.pt"


def csv_path(save_path: str) -> str:
    return f"{_stem(save_path)}.csv"


def atomic_save(payload: dict, path: str) -> None:
    """Serialize to ``<path>.tmp``, then rename over ``<path>``.

    ``os.replace`` is atomic on both POSIX and Windows, so a crash or Ctrl-C
    mid-write can only ever leave the *previous* checkpoint in place — never
    a half-written one. Without this, an interrupted save destroys the only
    file a long run can auto-resume from.
    """
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    try:
        torch.save(payload, tmp)
        os.replace(tmp, path)
    except BaseException:               # incl. KeyboardInterrupt
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def rotate_snapshots(save_path: str, keep: int) -> None:
    """Delete all but the ``keep`` most recent iter-stamped snapshots."""
    snaps = sorted(glob.glob(f"{_stem(save_path)}.iter*.pt"))
    for stale in snaps[:max(0, len(snaps) - keep)]:
        os.remove(stale)


def append_csv_row(path: str, row: dict) -> None:
    """Append one iteration's stats, writing the header only for a new file
    (so a resumed run continues the same CSV instead of restarting it)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fresh = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if fresh:
            writer.writeheader()
        writer.writerow(row)


def checkpoint_payload(agent: nn.Module, optimizer, iteration: int, args,
                       global_step: int, best_score: float = -math.inf) -> dict:
    return {
        "model": agent.state_dict(),
        "optim": optimizer.state_dict(),
        "iteration": iteration,
        "global_step": global_step,
        "best_score": best_score,
        "obs_dim": agent.obs_dim,
        "n_actions": agent.n_actions,
        "hidden": agent.hidden,
        "arch": args.arch,
        "head_version": models.ENTSET_HEAD_VERSION,
        "shared_encoder": getattr(args, "shared_encoder", False),
        "obs_schema": env_obs_schema(args),
        "env_kind": args.env,
        # Stamped next to env_kind, but checked with a WARN not a refusal
        # (checkpoints.check_ascension) -- unlike env_kind/schema/arch, v7
        # deliberately resumes training across ascensions.
        "ascension": getattr(args, "ascension", 0),
        # Not part of the model — recorded so a resume reproduces the batch
        # that trained these weights, and so the file says which one that was.
        "n_envs": args.n_envs,
        "n_steps": args.n_steps,
        # Phase-3 Task 3 (R11): which snapshot dataset (if any) trained
        # these weights. No refusal logic on a mismatched resume — a
        # resumed run may legitimately swap datasets or drop back to
        # synthetic starts (getattr: test fixtures may hand a bare
        # Namespace without every CLI flag, same pattern as shared_encoder
        # above).
        "start_snapshots": getattr(args, "start_snapshots", None),
    }


def save(agent: nn.Module, optimizer, iteration: int, args, *,
         global_step: int = 0, best_score: float = -math.inf) -> None:
    atomic_save(
        checkpoint_payload(agent, optimizer, iteration, args, global_step, best_score),
        args.save,
    )


if __name__ == "__main__":
    main()
