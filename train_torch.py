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
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

from sts2_rl import checkpoints, models
from sts2_rl.checkpoints import ModelSpec
from sts2_rl.full_env import COMBAT_POTION_BASE, MAX_ENEMIES
from sts2_rl.run_env import CHOICE_BASE, CHOICE_SLOTS, MAX_POTION_SLOTS, POTION_BASE
from sts2_rl.tensor_obs import TensorObs
from sts2_rl.vec_env import EnvSpec, make_vec_env, resolve_n_workers


def potion_entropy_bonus(probs, mask):
    """v16: binary entropy of the total probability mass on LEGAL potion
    actions (combat potion-pair block + out-of-combat belt block).

    probs/mask: (B, n_actions). Steps with no legal potion action are
    excluded from the mean (contribute nothing, not zero-averaged).
    Returns a scalar tensor; exactly 0 when no step has a legal potion
    action. Maximizing H_b(q) nudges 'consider drinking' upward without
    dictating WHICH drink — the hold-pricing reward terms decide where
    drinks actually pay.
    """
    pot = torch.zeros_like(mask)
    pot[:, COMBAT_POTION_BASE:COMBAT_POTION_BASE
        + MAX_POTION_SLOTS * MAX_ENEMIES] = True
    pot[:, POTION_BASE:POTION_BASE + MAX_POTION_SLOTS] = True
    legal_pot = mask & pot
    has = legal_pot.any(-1)
    if not bool(has.any()):
        return probs.new_zeros(())
    q = (probs * legal_pot).sum(-1).clamp(1e-6, 1.0 - 1e-6)
    hb = -(q * q.log() + (1.0 - q) * (1.0 - q).log())
    return (hb * has).sum() / has.sum()


def event_entropy_bonus(probs, mask, f_obs, event_present_col):
    """Mean entropy of the legal-CHOICE distribution on EVENT steps only.
    Event steps are flagged by the obs float `event.present` (the mask
    can't tell events from other choice screens). Renormalize probs over
    legal choice slots; exclude steps with <2 legal choices; average over
    included steps only (potion_ent precedent). Zero tensor if none."""
    choice = torch.zeros_like(mask)
    choice[:, CHOICE_BASE:CHOICE_BASE + CHOICE_SLOTS] = True
    legal = mask & choice
    is_event = f_obs[:, event_present_col] > 0.5
    multi = legal.sum(-1) >= 2
    keep = is_event & multi
    if not keep.any():
        return probs.new_zeros(())
    p = probs[keep] * legal[keep].float()
    p = p / p.sum(-1, keepdim=True).clamp_min(1e-12)
    ent = -(p.clamp_min(1e-12).log() * p).sum(-1)
    return ent.mean()


# ════════════════════════════════════════════════════════════════════════════
# Search distillation (v26, plan 2026-08-26-foresight-v25-v26, Task 11)
# ════════════════════════════════════════════════════════════════════════════
#
# `tools/search_worker.py` bottles a one-ply expectimax into `.npz` shards of
# (obs, mask, searched action distribution). This is the consuming half: the
# whole shard set is preloaded to the device ONCE, and each PPO minibatch pays
# a bounded number of rows of masked cross-entropy toward those distributions.
# The term adds NO parameters -- it pushes gradients through exactly the actor
# (shared encoder + tied action heads) that the policy-gradient term trains.

#: Per-minibatch row cap. The distillation cost is meant to be a fixed tax on
#: an update, not a function of how many shards happen to be on disk, so the
#: sample is `min(mb_size, this)` rows drawn WITH replacement rather than an
#: epoch over the set.
DISTILL_MAX_ROWS = 4096


@dataclass
class DistillSet:
    """A whole shard set, resident on the training device.

    The −1 pad convention is decoded HERE, once, so the loss never has to
    reason about it:

    * ``tgt_valid`` (bool) is the shard's ``tgt_idx >= 0`` -- the single
      unambiguous validity mask over both target arrays.
    * ``tgt_idx`` is clamped to ``>= 0`` so it is a legal ``gather`` index
      everywhere. A pad therefore READS some real action's log-prob; it is
      ``tgt_valid`` that stops the value being used (and its gradient path
      with it), not the index.
    * ``tgt_p`` is zeroed at every pad, so a −1 "probability" can never reach
      an arithmetic op even if a future caller skipped the validity mask.
    """

    f: "torch.Tensor"          # float32 (n, f_dim)
    i: "torch.Tensor"          # int64   (n, i_dim) -- embedding indices
    mask: "torch.Tensor"       # bool    (n, n_actions), the RECORD's legality
    tgt_idx: "torch.Tensor"    # int64   (n, k), clamped >= 0
    tgt_valid: "torch.Tensor"  # bool    (n, k)
    tgt_p: "torch.Tensor"      # float32 (n, k), 0 at every pad

    def __len__(self) -> int:
        return int(self.f.shape[0])

    @classmethod
    def from_arrays(cls, f, i, mask, tgt_idx, tgt_p, device) -> "DistillSet":
        idx = torch.as_tensor(np.asarray(tgt_idx), dtype=torch.int64,
                              device=device)
        valid = idx >= 0
        p = torch.as_tensor(np.asarray(tgt_p, dtype=np.float32),
                            dtype=torch.float32, device=device)
        return cls(
            f=torch.as_tensor(np.asarray(f, dtype=np.float32),
                              dtype=torch.float32, device=device),
            i=torch.as_tensor(np.asarray(i), dtype=torch.int64, device=device),
            mask=torch.as_tensor(np.asarray(mask), dtype=torch.bool,
                                 device=device),
            tgt_idx=idx.clamp_min(0),
            tgt_valid=valid,
            tgt_p=torch.where(valid, p, torch.zeros_like(p)),
        )


def check_distill_provenance(path, obs_schema, card_obs) -> dict:
    """Validate the shard set's ``provenance.json`` against THIS run's obs
    contract, and return it.

    This is the half of the contract the array dims cannot carry.
    ``search_worker.py``'s own docstring says the obs schema, card-obs mode
    and action count "all go into the provenance file next to the shards and
    the trainer is expected to check them" -- and its ``env_kwargs_for``
    warns why: ``hybrid`` and ``features`` have IDENTICAL obs dims (4736/1533
    at schema 13), so a shard set written under the other card encoding is
    dimensionally invisible. It would load, train, and produce a perfectly
    plausible falling loss curve while distilling toward targets computed on
    differently-encoded observations.

    Every failure is fatal, missing file included: the producer always writes
    `provenance.json`, so its absence means the directory is not a shard set
    this trainer can vouch for -- and an unverifiable shard set is exactly
    the thing this check exists to refuse. (Same for an unstamped file: a
    stamp that isn't there cannot be compared.)
    """
    import json

    prov_path = os.path.join(str(path), "provenance.json")
    if not os.path.isfile(prov_path):
        raise SystemExit(
            f"--distill {path}: no provenance.json beside the shards. "
            f"tools/search_worker.py always writes one; without it the shard "
            f"set's obs schema and card-obs mode cannot be checked, and a "
            f"mismatch there is dimensionally invisible.")
    try:
        # utf-8-sig, not utf-8: the producer writes plain UTF-8 (which this
        # decodes unchanged), but a hand-edited file round-tripped through a
        # Windows editor picks up a BOM, and refusing a shard set over a byte
        # order mark would be a maddening false alarm.
        prov = json.loads(open(prov_path, encoding="utf-8-sig").read())
    except ValueError as exc:
        raise SystemExit(f"--distill {path}: provenance.json is not valid "
                         f"JSON ({exc})")
    for key, want in (("obs_schema", obs_schema), ("card_obs", card_obs)):
        got = prov.get(key)
        if got is None:
            raise SystemExit(
                f"--distill {path}: provenance.json carries no {key!r} -- an "
                f"unstamped shard set cannot be checked against this run's "
                f"{key} ({want!r}); regenerate it with tools/search_worker.py")
        if got != want:
            raise SystemExit(
                f"--distill {path}: shard set was written at {key}={got!r} but "
                f"this run is {key}={want!r}. The obs encodings differ, so the "
                f"searched targets do not describe these observations "
                f"(hybrid/features share f/i dims, so no dim check can catch "
                f"this); regenerate the shards under {want!r}.")
    return prov


def load_distill_set(path, device, obs_dim=None, n_actions=None,
                     obs_schema=None, card_obs=None) -> DistillSet:
    """Read every shard of a shard set and materialize it on ``device``.

    Called ONCE at startup: the shards are float16/int32 on disk and become
    float32/int64 device tensors here, so the per-minibatch cost is a gather,
    not a decode. ``obs_dim``/``n_actions``, when given, are checked against
    the shards -- a shard set is only meaningful against the obs contract it
    was written under, and the dims are the part of that contract the trainer
    can verify for free. A mismatch is fatal rather than a warning: training
    on mis-aligned obs would poison the policy silently.

    ``obs_schema``/``card_obs`` are the part the dims CANNOT carry; passing
    either turns on the ``provenance.json`` check (see
    ``check_distill_provenance``). The trainer always passes both. They are
    optional only so a hand-built shard set (the tests') can be loaded
    without a provenance file -- there is no config for it to disagree with.
    """
    from tools.search_worker import iter_shards   # lazy: tools/ pulls forksim

    if obs_schema is not None or card_obs is not None:
        check_distill_provenance(path, obs_schema, card_obs)

    parts = {k: [] for k in ("f", "i", "mask", "tgt_idx", "tgt_p")}
    for shard in iter_shards(path):
        for k in parts:
            parts[k].append(shard[k])
    if not parts["f"]:
        raise SystemExit(f"--distill {path}: no .npz shards found there")
    arrays = {k: np.concatenate(v, axis=0) for k, v in parts.items()}
    if arrays["f"].shape[0] == 0:
        raise SystemExit(f"--distill {path}: the shard set holds 0 records")

    got = (int(arrays["f"].shape[1]), int(arrays["i"].shape[1]))
    if obs_dim is not None and got != (int(obs_dim[0]), int(obs_dim[1])):
        raise SystemExit(
            f"--distill {path}: shards carry obs dims {got} but this run's "
            f"obs layout is {(int(obs_dim[0]), int(obs_dim[1]))} -- the shard "
            f"set was written under a different obs schema/card-obs mode; "
            f"regenerate it with tools/search_worker.py")
    if n_actions is not None and int(arrays["mask"].shape[1]) != int(n_actions):
        raise SystemExit(
            f"--distill {path}: shards carry {int(arrays['mask'].shape[1])} "
            f"actions but this run's action space is {int(n_actions)}")
    return DistillSet.from_arrays(arrays["f"], arrays["i"], arrays["mask"],
                                  arrays["tgt_idx"], arrays["tgt_p"],
                                  device=device)


def sample_distill_rows(n: int, mb_size: int, device, generator=None):
    """``min(mb_size, DISTILL_MAX_ROWS)`` row indices, uniform WITH
    replacement over the whole set."""
    k = min(int(mb_size), DISTILL_MAX_ROWS)
    return torch.randint(0, int(n), (k,), device=device, generator=generator)


def distill_loss(agent, dset: DistillSet, rows) -> "torch.Tensor":
    """Masked cross-entropy from the policy toward the search distribution:

        -(tgt_p * log_softmax(action_logits(obs, mask)))[tgt_idx].sum(-1).mean()

    Two things make this the right gradient rather than merely the right
    number:

    * the log-softmax is taken over the logits masked by the SHARD's OWN
      legality vector -- the record's state, not any live env's -- so the
      normalizer matches the distribution the search actually chose within;
    * ``action_logits`` is the same actor path ``get_action_and_value`` builds
      its ``Categorical`` from, so the gradient lands on the very parameters
      the policy-gradient term trains. Nothing here touches the critic or the
      aux heads, so their grads stay ``None``.

    Padded columns contribute EXACTLY zero: the gathered value is replaced by
    a constant zero via ``torch.where`` (whose backward routes no gradient
    into the discarded branch at all), and ``tgt_p`` is already 0 there.
    """
    obs = TensorObs(dset.f[rows], dset.i[rows])
    mask = dset.mask[rows]
    logp = torch.log_softmax(agent.action_logits(obs, mask), dim=-1)
    gathered = logp.gather(-1, dset.tgt_idx[rows])
    gathered = torch.where(dset.tgt_valid[rows], gathered,
                           torch.zeros_like(gathered))
    return -(dset.tgt_p[rows] * gathered).sum(-1).mean()


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

# Subdirectory of the checkpoint's directory that per-iteration logs go in
# (see csv_path). Kept out of runs/ proper so the bulky, regenerable logs sit
# behind one gitignore entry instead of scattering next to the checkpoints.
RUN_LOGS_DIR = "run_logs"

# One row per iteration in run_logs/<stem>.csv. CSV, not TensorBoard, on purpose: zero
# dependencies, and a multi-day run's curve stays plottable from anything.
# `ep_ret` is the mean FLOORS COMPLETED over the last 100 episodes on the
# run-scale envs (not the reward sum -- reward weights shift between
# curriculum stages, so the return is not comparable across a run); on
# --env combat, which has no floors, it stays the raw episode return.
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
              "hp_lost",
              # v10 aux head (2026-08-14, post-s10): mean masked aux MSE per
              # iteration (NaN when --aux-hp-coef is 0). The s10 report-only
              # sanity gate ("aux_loss falling") was unverifiable post-hoc
              # because aux= only went to the console -- persist it.
              "aux",
              # v25 foresight heads (plan 2026-08-26-foresight-v25-v26): mean
              # masked BCE of the P(win) head and mean masked MSE of the
              # "hp lost before my next turn" head, per iteration (NaN when
              # the matching coef is 0).
              "aux_win", "aux_turn",
              # v16 potion-entropy bonus: mean binary entropy of the legal-
              # potion probability mass per iteration (NaN when
              # --potion-ent-coef is 0).
              "potion_ent",
              # v23: mean voluntary out-of-combat discards per episode
              # (EP_METRIC_KEYS "ep_potions_discarded") -- the v22 affordance
              # had no mid-run visibility, only the final eval.
              "potions_discarded",
              # v24 (plan Task 5): mean entropy of the legal-choice
              # distribution on event steps only (NaN when
              # --event-ent-coef is 0).
              "event_ent",
              # v26 search distillation (plan Task 11): mean masked cross-
              # entropy toward the searched action distribution per iteration
              # (NaN when --distill is off, and NaN for a critic-warmup
              # iteration, where the term is not applied at all).
              "distill"]


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
    ap.add_argument("--ascension-random", type=int, nargs=2, default=None,
                    metavar=("LO", "HI"),
                    help="v24: re-roll the episode ascension uniformly in "
                         "[LO, HI] at every reset (obs carry run.ascension "
                         "so the policy sees the level); overrides "
                         "--ascension for run-scale envs")
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
    ap.add_argument("--reward-boss", type=float, default=0.0,
                    help="v11: reward per act boss defeated (the final win "
                         "pays --reward-win plus this on top)")
    ap.add_argument("--reward-elite-attempt", type=float, default=0.0,
                    help="v11.1: reward per elite room entered, win or lose "
                         "(--reward-elite pays only on won fights)")
    ap.add_argument("--elite-rewards", type=float, nargs=3, default=None,
                    metavar=("ACT1", "ACT2", "ACT3"),
                    help="v24: per-act elite-WIN reward, replacing the flat "
                         "--reward-elite (e.g. 2 3 4 to track the "
                         "--floor-rewards act ramp). Unset keeps the flat "
                         "--reward-elite")
    ap.add_argument("--elite-attempt-rewards", type=float, nargs=3, default=None,
                    metavar=("ACT1", "ACT2", "ACT3"),
                    help="v24: per-act elite-ENTRY reward, replacing the flat "
                         "--reward-elite-attempt. Unset keeps the flat value")
    ap.add_argument("--reward-elite-escalator", type=float, default=0.0,
                    help="v24: within-act elite kill escalator -- the N-th "
                         "elite killed in an act pays base*(1+esc*(N-1)); "
                         "resets when act_index advances. 0.0 = default (inert)")
    ap.add_argument("--rest-heal-mask-above", type=float, default=None,
                    help="v8 plan Task 4: at a rest site, above this hp/max_hp "
                         "ratio, mask out REST_HEAL if another rest action is "
                         "legal (forces upgrade-path data instead of always "
                         "topping off). Unset = no masking (default)")
    ap.add_argument("--hp-potential-scale", type=float, default=0.0,
                    help="v8 plan Task 1: concave HP-potential shaping weight "
                         "(0 = off, the old behavior). knee stays at the "
                         "env's own default")
    ap.add_argument("--hp-potential-low-share", type=float, default=0.7,
                    help="v10: share of the HP-potential value below the "
                         "knee (env default 0.7; the s11-lowshare "
                         "contingency rung runs 0.8 -- steeper danger zone)")
    ap.add_argument("--potion-potential-scale", type=float, default=0.0,
                    help="v8 plan Task 2: potion-ledger shaping weight -- "
                         "+/-scale per potion gained/lost off the belt-count "
                         "delta (0 = off, the old behavior)")
    ap.add_argument("--rest-heal-shaping-knee-cap", action="store_true",
                    help="v9: rest heals earn HP-potential shaping only below "
                         "the knee (zero when starting at/above it)")
    ap.add_argument("--potion-death-expiry", action="store_true",
                    help="v9: -potion_potential_scale per potion still held "
                         "when the run ends in death")
    ap.add_argument("--potion-death-penalty", type=float, default=0.0,
                    help="v15.1: flat penalty per potion still held when the "
                         "run ends in death, on top of --potion-death-expiry "
                         "-- prices hoard-and-die strictly below "
                         "drink-and-die (0 = off)")
    ap.add_argument("--energy-waste-penalty", type=float, default=0.0,
                    help="v16: flat penalty per unspent energy point at every "
                         "player-turn end -- tiebreaker-sized energy "
                         "discipline; unconditional (empty-hand turns charge "
                         "too: the deck-building gradient) (0 = off)")
    ap.add_argument("--boss-hp-loss-penalty", type=float, default=0.0,
                    help="v20 (Task 3b): -K * (HP lost in a BOSS combat)/max_hp, "
                         "paid once when the combat resolves (won or lost). "
                         "Non-refundable by design -- the act-entry heal "
                         "refunds the hp-potential term's boss-fight losses, "
                         "this is the surviving price (0 = off)")
    ap.add_argument("--potion-option-value", type=float, default=0.0,
                    help="v21: -K * v(s) per potion DRINK, v = act-local hard "
                         "fights still ahead (elites ahead + boss unless in the "
                         "boss room, /3, cap 1) -- the opportunity value the "
                         "drink forgoes; no pickup credit (0 = off)")
    ap.add_argument("--potion-option-expiry", action="store_true",
                    help="v21: on a LOSS also charge -K * v(s) per potion still "
                         "held (hoard-and-die priced like drink-and-die)")
    ap.add_argument("--potion-timing-refund", type=float, default=0.0,
                    help="v24: pay back +K of the potion ledger's release "
                         "charge when a drink resolves DURING an elite/boss "
                         "combat (non-AnyTime potions only) -- a well-timed "
                         "drink nets +K over the potion's lifetime, every "
                         "other drink stays net 0 (0 = off)")
    ap.add_argument("--drill-snapshots", type=str, default=None,
                    help="v20 drill mode: schema-2 snapshot bank (harvest.py) "
                         "of mid-run combat start states (--env run only)")
    ap.add_argument("--drill-prob", type=float, default=0.0,
                    help="probability an episode starts at a sampled drill "
                         "combat instead of Neow (requires --drill-snapshots)")
    ap.add_argument("--drill-pools", type=str, default=None,
                    help="stratified pool masses, 'a1boss=0.2,a2elite=0.2,...' "
                         "(act is 1-based; rooms boss/elite/monster). Omit = "
                         "flat bank sampling. A named pool with zero bank "
                         "snapshots fails at construction")
    ap.add_argument("--drill-weights", type=str, default=None,
                    help="within-pool encounter oversampling, "
                         "'vantom_boss=2,crusher_rocket_boss=2,...' "
                         "(encounter id = multiplier)")
    ap.add_argument("--deck-random-prob", type=float, default=0.0,
                    help="probability an episode starts with a randomized deck "
                         "(card-exposure domain randomization; 0.0 = never)")
    ap.add_argument("--deck-inject", type=str, default=None,
                    help="v14: JSON of card-id packages appended to the "
                         "starting deck with --deck-inject-prob (spec "
                         "2026-08-15-v14-mechanics-exposure-design.md)")
    ap.add_argument("--deck-inject-prob", type=float, default=0.0)
    ap.add_argument("--deck-inject-midrun", type=str, default=None,
                    help="v15: JSON of card-id packages appended to the "
                         "live deck on a floor advance with "
                         "--deck-inject-midrun-prob (spec "
                         "2026-08-16-v15-extension-exposure-restfix.md)")
    ap.add_argument("--deck-inject-midrun-prob", type=float, default=0.0)
    ap.add_argument("--aux-hp-coef", type=float, default=0.0,
                    help="v10: weight of the auxiliary 'hp lost over the "
                         "next 3 floors' MSE (0 = head unused; run env + "
                         "entset only)")
    ap.add_argument("--aux-win-coef", type=float, default=0.0,
                    help="v25: weight of the auxiliary P(win|state) BCE head")
    ap.add_argument("--aux-hpturn-coef", type=float, default=0.0,
                    help="v25: weight of the auxiliary 'hp lost before my "
                         "next turn' MSE head")
    ap.add_argument("--quantile-critic", type=int, default=0,
                    metavar="N",
                    help="v26: replace the scalar value head with N quantile "
                         "estimates trained by the quantile-Huber (QR) loss; "
                         "the reported value is their mean (0 = off; entset "
                         "only). No value clipping is applied in this mode.")
    ap.add_argument("--distill", default=None, metavar="DIR",
                    help="v26: directory of search-distillation .npz shards "
                         "(tools/search_worker.py output). The whole set is "
                         "preloaded to the training device at startup; each "
                         "PPO minibatch distils a bounded sample of it into "
                         "the policy head (run env + entset only)")
    ap.add_argument("--distill-coef", type=float, default=0.0,
                    help="v26: weight of the search-distillation cross-entropy "
                         "term (0 = off; requires --distill)")
    ap.add_argument("--potion-ent-coef", type=float, default=0.0,
                    help="v16: extra entropy bonus on the total legal-potion-"
                         "action probability mass (binary entropy of q), "
                         "steps without a legal potion action excluded -- "
                         "exploration for drink timing without a reward term "
                         "(0 = off; run env + entset only)")
    ap.add_argument("--event-ent-coef", type=float, default=0.0,
                    help="v24: extra entropy bonus on the legal-choice "
                         "distribution, event steps only (flagged by the "
                         "run obs float event.present -- the action mask "
                         "can't tell events from other CHOICE_BASE screens) "
                         "-- exploration for event-option variety without a "
                         "reward term (0 = off; run env + entset only)")
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
    ap.add_argument("--cleanup-snapshots", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="on a run that finishes cleanly, delete this run's "
                         "iter-stamped snapshots — they only guard a collapse "
                         "mid-flight, and they dominate runs/ on disk. The "
                         "final --save checkpoint and <stem>.best.pt are kept, "
                         "so curriculum --resume handoff still works. A run "
                         "killed with Ctrl-C keeps every snapshot. Use "
                         "--no-cleanup-snapshots to keep them regardless")
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
        # ep_ret IS floors reached, and the column curriculum's win rate
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
    # v20 knobs are run-env only (mirrors the --start-snapshots guard: the
    # column env has no drill mode and no boss-combat context).
    if args.env != "run" and (
            args.boss_hp_loss_penalty or args.drill_snapshots
            or args.drill_prob or args.drill_pools or args.drill_weights):
        raise SystemExit(
            "--boss-hp-loss-penalty/--drill-snapshots/--drill-prob/"
            "--drill-pools/--drill-weights apply to --env run only.")
    if args.drill_prob and not args.drill_snapshots:
        raise SystemExit("--drill-prob requires --drill-snapshots.")
    if (args.drill_pools or args.drill_weights) and not args.drill_snapshots:
        raise SystemExit(
            "--drill-pools/--drill-weights require --drill-snapshots.")
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
            or args.reward_relic or args.reward_boss
            or args.reward_elite_attempt
            or args.elite_rewards is not None
            or args.elite_attempt_rewards is not None
            or args.reward_elite_escalator
            or args.rest_heal_mask_above is not None
            or args.hp_potential_scale or args.potion_potential_scale
            or args.potion_death_penalty
            or args.energy_waste_penalty
            or args.potion_option_value or args.potion_option_expiry
            or args.potion_timing_refund
            or args.deck_random_prob
            or args.deck_inject or args.deck_inject_prob
            or args.deck_inject_midrun or args.deck_inject_midrun_prob
            or getattr(args, "ascension_random", None) is not None):
        raise SystemExit(
            "--floor-rewards/--reward-win/--reward-upgrade/--reward-remove/"
            "--reward-elite/--reward-relic/--reward-boss/"
            "--reward-elite-attempt/--elite-rewards/--elite-attempt-rewards/"
            "--reward-elite-escalator/"
            "--rest-heal-mask-above/"
            "--hp-potential-scale/--potion-potential-scale/"
            "--potion-death-penalty/--energy-waste-penalty/"
            "--potion-option-value/--potion-option-expiry/"
            "--potion-timing-refund/"
            "--deck-random-prob/--deck-inject/--deck-inject-prob/"
            "--deck-inject-midrun/--deck-inject-midrun-prob/"
            "--ascension-random "
            "apply to the run-scale envs only.")
    if args.branch_prob and args.env != "column":
        raise SystemExit(
            f"--branch-prob applies to --env column only (got --env {args.env})")
    # v25: the two new aux heads share the v10 head's environment/arch
    # requirements -- all three read run-obs slots and live on entset.
    any_aux_coef = bool(args.aux_hp_coef or args.aux_win_coef
                        or args.aux_hpturn_coef)
    if any_aux_coef and args.env != "run":
        raise SystemExit("--aux-hp-coef / --aux-win-coef / --aux-hpturn-coef "
                         "need --env run (targets read the run obs layout's "
                         "run.floor / run.hp_ratio / combat.player slots)")
    if any_aux_coef and args.arch != "entset":
        raise SystemExit("--aux-hp-coef / --aux-win-coef / --aux-hpturn-coef "
                         "need --arch entset (aux heads live on "
                         "EntitySetActorCritic)")
    if args.quantile_critic < 0:
        raise SystemExit("--quantile-critic must be >= 0 (0 = the scalar critic)")
    if args.quantile_critic and args.arch != "entset":
        raise SystemExit("--quantile-critic needs --arch entset (the "
                         "distributional critic_q head lives on "
                         "EntitySetActorCritic)")
    # v26 search distillation: the shards are RUN-obs records and the loss
    # runs through entset's tied action heads, so it shares the aux heads'
    # environment/arch requirements. Both halves of the knob are refused
    # without the other: a coef with no shards and shards with no coef are
    # both silently-inert runs, the failure mode this file's guards exist for.
    if args.distill_coef < 0:
        raise SystemExit("--distill-coef must be >= 0 (0 = off)")
    if args.distill_coef and not args.distill:
        raise SystemExit("--distill-coef needs --distill DIR (the shard set to "
                         "distil from)")
    if args.distill and not args.distill_coef:
        raise SystemExit("--distill needs a positive --distill-coef, otherwise "
                         "the shards are loaded and never applied")
    if args.distill and args.env != "run":
        raise SystemExit("--distill applies to --env run only (the shards are "
                         "run-obs records)")
    if args.distill and args.arch != "entset":
        raise SystemExit("--distill needs --arch entset (the distillation loss "
                         "runs through EntitySetActorCritic.action_logits)")
    if args.potion_ent_coef and args.env != "run":
        raise SystemExit("--potion-ent-coef applies to the run-scale env only")
    if args.potion_ent_coef and args.arch != "entset":
        raise SystemExit("--potion-ent-coef needs --arch entset (the potion "
                         "index ranges are run-scale flat-layout constants)")
    if args.event_ent_coef and args.env != "run":
        raise SystemExit("--event-ent-coef applies to the run-scale env only")
    if args.event_ent_coef and args.arch != "entset":
        raise SystemExit("--event-ent-coef needs --arch entset (the choice "
                         "index range is a run-scale flat-layout constant)")
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


def cuda_mem_note(device) -> str:
    """``  vram <alloc>/<reserved>G`` for the iteration log, plus a RETRY
    count when the caching allocator has had to fall back.

    ``num_alloc_retries`` is the number the header comment about "GPU at 100%
    but 86 W" turned out to need: when a process is close to the card's
    capacity the allocator answers a failed block request by freeing cached
    blocks and re-trying ``cudaMalloc``, and that path SYNCHRONIZES the whole
    device. A run that starts retrying does not fail -- it silently drops to
    a fraction of its speed, which is indistinguishable from "the model got
    more expensive" in the sps column alone. Measured on this box 2026-08-27:
    v26 ran 96-107 s/iter through the critic warm-up and then 452-926 s/iter
    on the first three distillation iterations, at 7717/8192 MiB.

    Host-side bookkeeping only -- ``memory_stats`` reads counters the
    allocator already keeps, so this costs no sync and cannot itself perturb
    what it measures.
    """
    if device.type != "cuda":
        return ""
    st = torch.cuda.memory_stats(device)
    gb = 1024 ** 3
    note = (f"  vram {torch.cuda.memory_allocated(device) / gb:.2f}"
            f"/{torch.cuda.memory_reserved(device) / gb:.2f}G")
    retries = int(st.get("num_alloc_retries", 0))
    if retries:
        note += f"  ALLOC-RETRIES {retries}"
    return note


def logged_mean(values: "list[torch.Tensor]") -> float:
    """Mean of per-minibatch log values that were kept on the DEVICE.

    These lists used to hold Python floats, which meant a ``.item()`` -- a
    full ``cudaStreamSynchronize`` -- inside the minibatch loop for every
    logged quantity. At 4 epochs x 16 minibatches that is 64 drains of the
    CUDA queue per iteration *per quantity*, and with the v25 aux heads and
    the v26 distillation term live there were six such quantities: ~384
    stalls an iteration, none of which any training decision reads. The
    stall is the cost, not the arithmetic -- while the CPU is blocked it
    cannot run ahead and queue the next minibatch's kernels, so the GPU
    drains to one-kernel-at-a-time (measured 2026-08-27 mid-v26: 100% duty
    cycle at 86 W of ~220 W and 7% memory bandwidth, main thread pinned at
    98.8% of one core busy-waiting).

    So the appends now stash DETACHED device tensors and the crossing to the
    CPU happens once, here, at logging time. The number is unchanged -- the
    mean of the same per-minibatch scalars -- and so is every gradient:
    nothing in the update loop reads these. ``.detach()`` at the append site
    is what keeps this from pinning 64 minibatches' autograd graphs.

    ``kl_exceeded``'s input is deliberately NOT routed through here: that one
    IS read every minibatch, to decide whether to break the epoch, so its
    sync is load-bearing and stays.
    """
    if not values:
        return float("nan")
    # float64 accumulation, matching the np.mean this replaced: the CSV
    # columns are compared across generations, and a float32 sum over 64
    # minibatches would shift them by a hair for no reason. 64 elements, so
    # the widening costs nothing.
    return float(torch.stack(values).double().mean())


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


def _parse_kv_floats(text: str | None, flag: str) -> "tuple[tuple[str, float], ...] | None":
    """'a1boss=0.2,a2elite=0.2' -> (('a1boss', 0.2), ('a2elite', 0.2)).
    Loud on a malformed pair — a silently-dropped pool mass would skew the
    drill mix without a trace."""
    if text is None:
        return None
    pairs = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit(f"{flag}: malformed entry {chunk!r} (want key=value)")
        key, _, value = chunk.partition("=")
        try:
            pairs.append((key.strip(), float(value)))
        except ValueError:
            raise SystemExit(f"{flag}: non-numeric value in {chunk!r}")
    if not pairs:
        raise SystemExit(f"{flag}: no key=value entries in {text!r}")
    return tuple(pairs)


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
        ascension_sample=(tuple(args.ascension_random)
                          if getattr(args, "ascension_random", None) else None),
        floor_rewards_by_act=(tuple(args.floor_rewards)
                              if getattr(args, "floor_rewards", None) is not None
                              else None),
        reward_win_run=getattr(args, "reward_win", None),
        reward_upgrade=getattr(args, "reward_upgrade", 0.0),
        reward_remove=getattr(args, "reward_remove", 0.0),
        reward_elite=getattr(args, "reward_elite", 0.0),
        reward_relic=getattr(args, "reward_relic", 0.0),
        reward_boss=getattr(args, "reward_boss", 0.0),
        reward_elite_attempt=getattr(args, "reward_elite_attempt", 0.0),
        elite_rewards_by_act=(tuple(args.elite_rewards)
                              if getattr(args, "elite_rewards", None) is not None
                              else None),
        elite_attempt_rewards_by_act=(
            tuple(args.elite_attempt_rewards)
            if getattr(args, "elite_attempt_rewards", None) is not None
            else None),
        reward_elite_escalator=getattr(args, "reward_elite_escalator", 0.0),
        rest_heal_mask_above=getattr(args, "rest_heal_mask_above", None),
        hp_potential_scale=getattr(args, "hp_potential_scale", 0.0),
        potion_potential_scale=getattr(args, "potion_potential_scale", 0.0),
        deck_random_prob=getattr(args, "deck_random_prob", 0.0),
        deck_inject=getattr(args, "deck_inject", None),
        deck_inject_prob=getattr(args, "deck_inject_prob", 0.0),
        deck_inject_midrun=getattr(args, "deck_inject_midrun", None),
        deck_inject_midrun_prob=getattr(args, "deck_inject_midrun_prob", 0.0),
        rest_heal_shaping_knee_cap=getattr(args, "rest_heal_shaping_knee_cap", False),
        potion_death_expiry=getattr(args, "potion_death_expiry", False),
        potion_death_penalty=getattr(args, "potion_death_penalty", 0.0),
        energy_waste_penalty=getattr(args, "energy_waste_penalty", 0.0),
        potion_option_value=getattr(args, "potion_option_value", 0.0),
        potion_option_expiry=getattr(args, "potion_option_expiry", False),
        potion_timing_refund=getattr(args, "potion_timing_refund", 0.0),
        hp_potential_low_share=getattr(args, "hp_potential_low_share", 0.7),
        boss_hp_loss_penalty=getattr(args, "boss_hp_loss_penalty", 0.0),
        drill_snapshots=getattr(args, "drill_snapshots", None),
        drill_prob=getattr(args, "drill_prob", 0.0),
        drill_pools=_parse_kv_floats(
            getattr(args, "drill_pools", None), "--drill-pools"),
        drill_encounter_weights=_parse_kv_floats(
            getattr(args, "drill_weights", None), "--drill-weights"),
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
        # getattr for the same reason as shared_encoder above (hand-built
        # test Namespaces); the real CLI always sets it via --quantile-critic.
        n_quantiles=getattr(args, "quantile_critic", 0),
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
        checkpoints.check_ascension(
            ckpt, args.ascension,
            ascension_sample=(tuple(args.ascension_random)
                              if getattr(args, "ascension_random", None)
                              else None))
        n_fresh_aux = checkpoints.load_model_state_lenient(agent, ckpt["model"])
        if n_fresh_aux:
            print(f"aux heads fresh-initialized ({n_fresh_aux} params not in checkpoint)")
        opt_state = ckpt["optim"]
        n_live = sum(1 for _ in agent.parameters())
        if patch_optimizer_group_for_fresh_aux(opt_state, n_live, n_fresh_aux):
            print(f"optimizer state patched: {n_fresh_aux} fresh aux params appended")
        optimizer.load_state_dict(opt_state)
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

    # v25: any of the three aux coefs turns the aux heads on; the slice tuple
    # is (run.floor, run.hp_ratio, combat.player.turn, combat.player.hp_ratio).
    ANY_AUX = (args.aux_hp_coef > 0 or args.aux_win_coef > 0
               or args.aux_hpturn_coef > 0)
    # v26: whether this run's critic is distributional. Read off the built
    # agent, not the flag, so a resumed checkpoint's own structure wins.
    QUANTILE = getattr(agent, "n_quantiles", 0) > 0
    aux_slices = None
    if ANY_AUX:
        from sts2_rl.run_env import run_obs_layout
        _l = run_obs_layout(args.card_obs)
        aux_slices = (_l.f_slices["run.floor"], _l.f_slices["run.hp_ratio"],
                      _l.f_slices["combat.player.turn"],
                      _l.f_slices["combat.player.hp_ratio"])

    EVENT_PRESENT_COL = None
    if args.event_ent_coef > 0:
        from sts2_rl.run_env import run_obs_layout
        _l = run_obs_layout(args.card_obs)
        EVENT_PRESENT_COL = _l.f_slices["event.present"].start

    # v26 search distillation (plan Task 11): the whole shard set is loaded
    # ONCE, here, as device tensors — the per-minibatch cost is then a gather
    # rather than a decode. Loaded AFTER the resume so a mis-matched shard set
    # is refused against this run's real obs contract.
    DISTILL = None
    if args.distill and args.distill_coef > 0:
        DISTILL = load_distill_set(args.distill, device, obs_dim=obs_dim,
                                   n_actions=n_actions,
                                   obs_schema=env_obs_schema(args),
                                   card_obs=args.card_obs)
        print(f"Distilling from {args.distill}: {len(DISTILL)} searched "
              f"decisions (k={DISTILL.tgt_idx.shape[1]}), coef "
              f"{args.distill_coef:g}, up to {DISTILL_MAX_ROWS} rows/minibatch")

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
    # v25 win head: succ_buf shares done_buf's index convention EXACTLY --
    # entry t records the PREVIOUS step's done/success, so done_buf[t]==1 means
    # obs t opens a new episode and succ_buf[t] scores the episode that just
    # closed. win_outcome() reads the pair on that shared index.
    succ_buf = torch.zeros((N, E), device=device)
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
    next_succ = torch.zeros(E, device=device)

    # episodic logging. ep_ret_running accumulates raw env reward (not the
    # training-time bootstrap fold-in); it is only the combat-env fallback for
    # ret_hist, which otherwise holds end-of-episode floors (see CSV_FIELDS).
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
    # v23: voluntary discards per episode (EP_METRIC_KEYS[17]), same
    # windowing as v8_relic_hist.
    discard_hist: deque[float] = deque(maxlen=100)

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
                succ_buf[t] = next_succ
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
                    # ep_ret is FLOORS COMPLETED on run-scale envs (metrics
                    # column EP_METRIC_KEYS[-1] = "floor"), so the training
                    # curve is on the same scale as eval's mean floor. The
                    # combat env reports no floor -> raw episode return.
                    floor_end = float(batch.metrics[i, -1])
                    ret_hist.append(float(ep_ret_running[i])
                                    if math.isnan(floor_end) else floor_end)
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
                    if not math.isnan(m[17]):
                        discard_hist.append(float(m[17]))
                    ep_ret_running[i] = 0.0
                    ep_len_running[i] = 0

                rew_buf[t] = torch.as_tensor(rewards, device=device)
                next_obs = batch.obs.to(device)
                next_mask = torch.as_tensor(batch.masks, dtype=torch.bool, device=device)
                next_done = torch.as_tensor(dones.astype(np.float32), device=device)
                # StepBatch.successes is info["is_success"] harvested on the
                # same step the done fires (vec_env.py:340-341), so it is
                # aligned with `dones` and rides the same one-step carry.
                next_succ = torch.as_tensor(
                    batch.successes.astype(np.float32), device=device)

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

            b_auxt = b_auxv = b_wint = b_winv = b_turnt = b_turnv = None
            if ANY_AUX:
                from sts2_rl.aux_targets import (hp_lost_next_floors,
                                                 hp_lost_next_turn, win_outcome)
                dn = done_buf.cpu().numpy()
                if args.aux_hp_coef > 0:
                    fl = obs_buf.f[:, :, aux_slices[0]].squeeze(-1).cpu().numpy()
                    hp = obs_buf.f[:, :, aux_slices[1]].squeeze(-1).cpu().numpy()
                    aux_t, aux_v = hp_lost_next_floors(fl, hp, dn)
                    b_auxt = torch.as_tensor(aux_t, device=device).reshape(-1)
                    b_auxv = torch.as_tensor(aux_v, device=device, dtype=torch.float32).reshape(-1)
                if args.aux_win_coef > 0:
                    win_t, win_v = win_outcome(dn, succ_buf.cpu().numpy())
                    b_wint = torch.as_tensor(win_t, device=device).reshape(-1)
                    b_winv = torch.as_tensor(win_v, device=device, dtype=torch.float32).reshape(-1)
                if args.aux_hpturn_coef > 0:
                    tn = obs_buf.f[:, :, aux_slices[2]].squeeze(-1).cpu().numpy()
                    chp = obs_buf.f[:, :, aux_slices[3]].squeeze(-1).cpu().numpy()
                    turn_t, turn_v = hp_lost_next_turn(tn, chp, dn)
                    b_turnt = torch.as_tensor(turn_t, device=device).reshape(-1)
                    b_turnv = torch.as_tensor(turn_v, device=device, dtype=torch.float32).reshape(-1)

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
            clipfracs: list["torch.Tensor"] = []
            aux_losses: list["torch.Tensor"] = []
            win_losses: list["torch.Tensor"] = []
            turn_losses: list["torch.Tensor"] = []
            potion_ent_losses: list["torch.Tensor"] = []
            event_ent_losses: list["torch.Tensor"] = []
            distill_losses: list["torch.Tensor"] = []
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
                    extra = {}
                    if ANY_AUX:
                        extra["with_aux"] = True
                    if QUANTILE:
                        extra["with_quantiles"] = True
                    if args.potion_ent_coef > 0 or args.event_ent_coef > 0:
                        extra["with_dist"] = True
                    out = agent.get_action_and_value(b_obs[mb], b_mask[mb], b_act[mb], **extra)
                    _, newlogp, entropy, newval = out[:4]
                    i = 4
                    # v25: with_aux appends all THREE preds in the frozen order
                    # (hp3, win logit, hpturn); v26's quantiles come next;
                    # with_dist's dist stays last.
                    aux_pred = win_pred = turn_pred = None
                    if ANY_AUX:
                        aux_pred, win_pred, turn_pred = out[i], out[i + 1], out[i + 2]
                        i += 3
                    quantiles = None
                    if QUANTILE:
                        quantiles = out[i]
                        i += 1
                    dist = out[i] if (args.potion_ent_coef > 0
                                       or args.event_ent_coef > 0) else None
                    logratio = newlogp - b_logp[mb]
                    ratio = logratio.exp()
                    with torch.no_grad():
                        kls.append(float(((ratio - 1) - logratio).mean()))
                        clipfracs.append(
                            ((ratio - 1.0).abs() > args.clip).float().mean().detach())

                    mb_adv = b_adv[mb]
                    mb_adv = (mb_adv - mb_adv.mean()) / (mb_adv.std() + 1e-8)

                    pg_loss = torch.max(
                        -mb_adv * ratio,
                        -mb_adv * torch.clamp(ratio, 1 - args.clip, 1 + args.clip),
                    ).mean()

                    if QUANTILE:
                        # v26: the quantile-Huber (QR) loss replaces the
                        # clipped value loss WHOLESALE, and deliberately
                        # carries no value clipping. PPO's value clipping is
                        # defined on the SCALAR head -- it trust-regions
                        # `newval` around the rollout's `b_val` -- and there
                        # is no meaningful per-quantile analogue: clipping
                        # each quantile toward a single old scalar would
                        # squash the very spread the distributional critic
                        # exists to learn. The QR loss's own Huber term
                        # already bounds the per-sample gradient.
                        #
                        # Nothing here reads `newval`, so the still-registered
                        # scalar `agent.critic` receives no gradient at all:
                        # its grads stay None and Adam skips it, momentum
                        # included (same mechanism as --critic-warmup's actor).
                        v_loss = quantile_huber_loss(quantiles, b_ret[mb])
                    else:
                        # clipped value loss
                        v_unclipped = (newval - b_ret[mb]) ** 2
                        v_clip = b_val[mb] + torch.clamp(newval - b_val[mb], -args.clip, args.clip)
                        v_clipped = (v_clip - b_ret[mb]) ** 2
                        v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()

                    ent_loss = entropy.mean()
                    aux_loss = torch.zeros((), device=device)
                    if args.aux_hp_coef > 0:
                        m = b_auxv[mb]
                        aux_loss = ((aux_pred - b_auxt[mb]).pow(2) * m).sum() / m.sum().clamp(min=1.0)
                        aux_losses.append(aux_loss.detach())
                    win_loss = torch.zeros((), device=device)
                    if args.aux_win_coef > 0:
                        m = b_winv[mb]
                        win_loss = (nn.functional.binary_cross_entropy_with_logits(
                            win_pred, b_wint[mb], reduction="none") * m
                        ).sum() / m.sum().clamp(min=1.0)
                        win_losses.append(win_loss.detach())
                    turn_loss = torch.zeros((), device=device)
                    if args.aux_hpturn_coef > 0:
                        m = b_turnv[mb]
                        turn_loss = ((turn_pred - b_turnt[mb]).pow(2) * m
                                     ).sum() / m.sum().clamp(min=1.0)
                        turn_losses.append(turn_loss.detach())
                    potion_ent_loss = torch.zeros((), device=device)
                    if args.potion_ent_coef > 0:
                        potion_ent_loss = potion_entropy_bonus(dist.probs, b_mask[mb])
                        potion_ent_losses.append(potion_ent_loss.detach())
                    event_ent_loss = torch.zeros((), device=device)
                    if args.event_ent_coef > 0:
                        event_ent_loss = event_entropy_bonus(
                            dist.probs, b_mask[mb], b_obs[mb].f, EVENT_PRESENT_COL)
                        event_ent_losses.append(event_ent_loss.detach())
                    # v26: distillation is an ACTOR term, so unlike the aux
                    # heads it is skipped during the critic warm-up — applying
                    # it there would move the policy in exactly the iterations
                    # the warm-up exists to hold it still (and would put the
                    # actor back in the graph, undoing the "policy comes out
                    # bit-identical" property above).
                    distill_l = torch.zeros((), device=device)
                    if DISTILL is not None and not critic_only:
                        distill_l = distill_loss(
                            agent, DISTILL,
                            sample_distill_rows(len(DISTILL), mb_size,
                                                device=device))
                        distill_losses.append(distill_l.detach())
                    if critic_only:
                        loss = (args.vf_coef * v_loss
                                + args.aux_hp_coef * aux_loss
                                + args.aux_win_coef * win_loss
                                + args.aux_hpturn_coef * turn_loss)
                    else:
                        loss = (pg_loss - ent_coef * ent_loss
                                - args.potion_ent_coef * potion_ent_loss
                                - args.event_ent_coef * event_ent_loss
                                + args.vf_coef * v_loss
                                + args.aux_hp_coef * aux_loss
                                + args.aux_win_coef * win_loss
                                + args.aux_hpturn_coef * turn_loss
                                + args.distill_coef * distill_l)

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
            discard_mean = (
                float(np.mean(discard_hist)) if discard_hist else float("nan"))
            lr = optimizer.param_groups[0]["lr"]
            aux_mean = logged_mean(aux_losses)
            aux_win_mean = logged_mean(win_losses)
            aux_turn_mean = logged_mean(turn_losses)
            potion_ent_mean = logged_mean(potion_ent_losses)
            event_ent_mean = logged_mean(event_ent_losses)
            distill_mean = logged_mean(distill_losses)
            clipfrac_mean = logged_mean(clipfracs)
            print(
                f"iter {iteration:4d}  step {global_step:>9d}  sps {sps:>5d}  "
                f"ep_ret {ret:7.3f}  win {wr:5.2f}  ep_len {eplen:6.1f}  "
                f"pg {pg_loss.item():+.3f}  v {v_loss.item():.3f}  "
                f"ent {ent_loss.item():.3f}  kl {approx_kl:.4f}  "
                f"clipfrac {clipfrac_mean:.3f}  "
                f"e_unspent {energy_unspent:4.2f}  take {card_take:4.2f}"
                + (f"  aux={aux_mean:.4f}" if args.aux_hp_coef > 0 else "")
                + (f"  aux_win={aux_win_mean:.4f}" if args.aux_win_coef > 0 else "")
                + (f"  aux_turn={aux_turn_mean:.4f}" if args.aux_hpturn_coef > 0 else "")
                + (f"  pot_ent={potion_ent_mean:.4f}" if args.potion_ent_coef > 0 else "")
                + (f"  ev_ent={event_ent_mean:.4f}" if args.event_ent_coef > 0 else "")
                + (f"  distill={distill_mean:.4f}" if DISTILL is not None else "")
                # pg/ent are still reported during the warm-up (they say how
                # stale the advantages are) but were not applied — mark it so
                # a flat ep_ret here doesn't read as a stalled run.
                + ("  [critic-warmup]" if critic_only else "")
                + cuda_mem_note(device),
                flush=True,
            )
            if args.save:
                append_csv_row(csv_path(args.save), dict(
                    iter=iteration, global_step=global_step,
                    wall_seconds=round(elapsed, 3), sps=sps,
                    ep_ret=ret, win=wr, ep_len=eplen,
                    pg=pg_loss.item(), v=v_loss.item(), ent=ent_loss.item(),
                    kl=approx_kl, clipfrac=clipfrac_mean, lr=lr,
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
                    aux=aux_mean,
                    aux_win=aux_win_mean,
                    aux_turn=aux_turn_mean,
                    potion_ent=potion_ent_mean,
                    potions_discarded=discard_mean,
                    event_ent=event_ent_mean,
                    distill=distill_mean,
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
            # Only reachable once every iteration ran: the loop has no break,
            # so a Ctrl-C or a crash raises past this and keeps the snapshots
            # (the whole point of having them). Final .pt and .best.pt stay.
            if args.cleanup_snapshots:
                n_removed = cleanup_snapshots(args.save)
                if n_removed:
                    print(f"Run finished — removed {n_removed} iter snapshot(s); "
                          f"kept {args.save} and {best_path(args.save)}")
    finally:
        envs.close()


def _stem(save_path: str) -> str:
    """``runs/x.pt`` -> ``runs/x`` — the prefix every sidecar file hangs off."""
    return save_path[:-3] if save_path.endswith(".pt") else save_path


def snapshot_path(save_path: str, iteration: int) -> str:
    """Zero-padded so snapshots sort lexicographically by iteration."""
    return f"{_stem(save_path)}.iter{iteration:06d}.pt"


def quantile_huber_loss(pred_q: torch.Tensor, target: torch.Tensor,
                        kappa: float = 1.0) -> torch.Tensor:
    """Quantile-Huber (QR-DQN eq. 10) of predicted quantiles against a
    SCALAR sample target per row (the empirical lambda-return). pred_q is
    (B, N); target is (B,)."""
    n = pred_q.shape[-1]
    taus = (2 * torch.arange(n, device=pred_q.device) + 1) / (2.0 * n)
    u = target.unsqueeze(-1) - pred_q                      # (B, N)
    huber = torch.where(u.abs() <= kappa, 0.5 * u * u,
                        kappa * (u.abs() - 0.5 * kappa))
    return (torch.abs(taus - (u.detach() < 0).float()) * huber / kappa).mean()


def patch_optimizer_group_for_fresh_aux(opt_state: dict, n_live: int,
                                        n_fresh: int) -> bool:
    """Widen a saved single-group Adam state to cover freshly-added aux params.

    A checkpoint that predates one of the aux heads saved fewer parameters than
    the live model has, and ``Optimizer.load_state_dict`` refuses a param group
    whose length does not match. The aux heads are registered LAST and in a
    frozen order (``models.EntitySetActorCritic``: aux_hp3 → aux_win →
    aux_hpturn), so the saved ids still address the same tensors and the fresh
    tail simply takes the next ids with no moment state (Adam initializes those
    lazily on the first step).

    ``n_fresh`` MUST be the count of parameters actually missing from the
    checkpoint (``checkpoints.load_model_state_lenient``'s return), not the
    count of all ``aux_*`` params: a v23-era checkpoint already carries the v10
    ``aux_hp3_head``, so counting every aux param over-shoots by that head's
    four tensors and the patch silently declines to fire (v25 smoke, 2026-08-26).

    Returns True when the state was patched.
    """
    if n_fresh <= 0:
        return False
    groups = opt_state.get("param_groups") or []
    if len(groups) != 1:
        return False
    saved = groups[0]["params"]
    if len(saved) >= n_live or len(saved) + n_fresh != n_live:
        return False
    groups[0]["params"] = list(saved) + list(range(len(saved), n_live))
    return True


def best_path(save_path: str) -> str:
    return f"{_stem(save_path)}.best.pt"


def csv_path(save_path: str) -> str:
    """``runs/x.pt`` -> ``runs/run_logs/x.csv``.

    Parked in a subdirectory rather than beside the checkpoint because these
    grow one row per iteration across every run ever trained, and the whole
    directory is gitignored — they are bulky and regenerable. Created on
    demand by append_csv_row.
    """
    stem = _stem(save_path)
    return os.path.join(os.path.dirname(stem), RUN_LOGS_DIR,
                        os.path.basename(stem) + ".csv")


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


def cleanup_snapshots(save_path: str) -> int:
    """Delete *this run's* iter-stamped snapshots; return how many went.

    Snapshots exist to survive a late collapse *while the run is in flight* —
    once it has finished cleanly they are pure disk (they were the bulk of a
    4.4 GB ``runs/``). Deliberately narrow: the final ``--save`` checkpoint and
    ``.best.pt`` stay, because the curriculum scripts chain stages through
    ``--resume runs/..._sNN.pt`` and deleting the final file breaks the handoff.

    The glob hangs off this run's stem, so sibling runs sharing ``runs/`` are
    untouched. Only ever called on the normal completion path — an interrupted
    run raises straight past it and keeps every snapshot.
    """
    snaps = glob.glob(f"{_stem(save_path)}.iter*.pt")
    for snap in snaps:
        os.remove(snap)
    return len(snaps)


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
        # v26: 0 = the scalar critic. Checked with a hard refusal
        # (checkpoints.check_checkpoint) -- structurally different critic.
        "n_quantiles": getattr(args, "quantile_critic", 0),
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
        # v20: what drill bank/mix and boss-hp price this ckpt trained on.
        "boss_hp_loss_penalty": getattr(args, "boss_hp_loss_penalty", 0.0),
        "drill_snapshots": getattr(args, "drill_snapshots", None),
        "drill_prob": getattr(args, "drill_prob", 0.0),
        "drill_pools": getattr(args, "drill_pools", None),
        "drill_weights": getattr(args, "drill_weights", None),
        # v21: the potion opportunity-value price this ckpt trained under.
        "potion_option_value": getattr(args, "potion_option_value", 0.0),
        "potion_option_expiry": getattr(args, "potion_option_expiry", False),
    }


def save(agent: nn.Module, optimizer, iteration: int, args, *,
         global_step: int = 0, best_score: float = -math.inf) -> None:
    atomic_save(
        checkpoint_payload(agent, optimizer, iteration, args, global_step, best_score),
        args.save,
    )


if __name__ == "__main__":
    main()
