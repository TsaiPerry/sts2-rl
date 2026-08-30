"""search_worker.py — generate search-distillation shards (plan
2026-08-26-foresight-v25-v26, Task 10).

Tier-B measured what a one-ply expectimax buys (`tools/eval_search.py`); this
tool BOTTLES it. It walks real mid-run combats out of a snapshot bank, picks
the decisions worth paying rollouts on, runs `forksim.expectimax` there, and
writes the searched action distribution to disk as `.npz` shards. Task 11's
trainer flag takes the OUTPUT DIRECTORY and distils those distributions into
the policy head, so the deployed agent inherits the search's answers without
paying the search's wall-clock.

## What a record is

One record = one combat decision the search actually scored:

    f        float16 (n, f_dim)      the run obs float block at that decision
    i        int32   (n, i_dim)      the run obs id block
    mask     bool    (n, n_actions)  the env's legality vector
    tgt_idx  int32   (n, k)          the searched action ids, −1 padded
    tgt_p    float16 (n, k)          softmax(mean rollout score) over those
                                     ids at `--temperature` (default 1.0,
                                     the pre-flag behaviour), −1 padded

`f`/`i` are stored VERBATIM from `env._build_obs()` (float16 is the storage
dtype; the trainer casts back to float32), so a shard set is only meaningful
against the obs schema it was written under — schema, f_dim/i_dim and
n_actions all go into the provenance file next to the shards and the trainer
is expected to check them.

**The −1 pad convention.** A decision can have fewer than `k` candidates (few
legal actions, or `--mass-cap` shrinking the set), so both target arrays are
padded to `k` with −1. −1 is neither a legal action id nor a probability, so
`tgt_idx >= 0` is an unambiguous validity mask on either array and no real
value can ever be mistaken for padding. `tgt_p`'s valid entries sum to 1 over
the candidates present ("renormalized over the k"), never over the padding.

## Which decisions get searched

Content-agnostic, deliberately — no encounter ids anywhere in this file, so
the shard set never encodes "these particular fights are the hard ones":

  * every decision inside an ELITE or BOSS fight from the bank, plus
  * every decision whose MASKED-POLICY ENTROPY (entropy over the LEGAL
    actions only, from the same masked softmax the trainer and eval use) is
    in the top half of the batch this invocation collected.

The median split is over the WHOLE batch, elite/boss decisions included —
"the batch" is the pool of decisions this run walked. That makes selection a
pure function of the pool, which is why the tool works in ROUNDS, each round a
collect phase followed by a score phase over the pool that round collected
(`run_worker` repeats rounds until the kept-record budget or `--max-fights` is
reached — see the termination note there):

  1. **collect** — play fights under the deployed (sampling) policy, one
     forward per decision, recording obs/mask/entropy/room and the action
     PREFIX that reproduces the state. Cheap. Keeps going until the selection
     rule would yield `--decisions` records (or `--max-fights` trips), then
     the selected list is truncated to `--decisions` IN COLLECTION ORDER —
     the overshoot is at most one fight's worth of decisions, so the
     truncation drops a tail of the last fight rather than skewing the mix.
  2. **score** — for each selected decision, `forksim.expectimax` from the
     fork at that prefix. Expensive (k·m rollouts each), so it only ever runs
     on decisions the rule already kept.

Forced decisions (one legal action) are never recorded: there is nothing to
distil, and `expectimax` declines them anyway.

## `--min-score-gap G` — the decisiveness filter (2026-08-28, v27 Task 4b)

A third gate sits AFTER the search, on its result rather than on the state:
let δ = top1 − top2 of the raw mean rollout scores over the candidates the
search actually scored (δ = +∞ when there is only one). If `G > 0` and
δ <= G the decision is DROPPED — no record written, and it does not count
against `--decisions`, which therefore counts KEPT records. The search itself
already happened, so its cost is real and is counted separately in
`stats.decisions_searched` / `stats.skipped_indecisive`. `G = 0.0` is the
default and means NO FILTER AT ALL (exact ties included), so every pre-flag
shard set stays reproducible.

Why it exists: the v27 temperature calibration (`docs/superpowers/plans/
v27-run-log.md`, 08-28 entry) ran a one-variable T sweep over a fixed
200-decision slice and MISSED the pre-registered "median top1−top2 target-mass
gap ≥ 0.25" bar at every temperature — best 0.054 at T = 0.1. The cause is not
the softmax but its input: the median raw score gap is ≈ 0.016 return units,
and **19.5% of records have every candidate scored exactly equal**, where a
softmax is literally temperature-invariant. Sharpening cannot separate scores
that are not separated. Filtering can: on the same measured scores, keeping
δ > 0.05 retains **41%** of records and lifts the median target gap to
**0.317 at T = 0.25** — over the bar. Hence v27's pinned pair,
`--min-score-gap 0.05 --temperature 0.25`.

Consequence for the driver: because a rejection is only known after the
rollouts are paid for, `run_worker` can no longer fill its budget in one
collect-then-score pass. It runs ROUNDS instead — see the termination note
there. `--max-fights` remains the hard bound, so a bank of purely indecisive
decisions costs at most that many fights and then stops short of `--decisions`
rather than looping.

## Determinism

Everything is a pure function of `(ckpt, bank, --seed, --k, --m, --asc,
--decisions, --max-fights)`: the fight list is positional — fight `n` takes
snapshot `n % len(bank)`, the same cycling rule `eval_search.build_fight_list`
uses, written out inline here because collection runs open-ended (it stops on
the selection rule, not on a pre-sized fight count) — each fight's reset seed
comes from `eval_search._fight_seed(--seed, fight)`,
the behaviour policy's per-decision draw is reseeded from
`eval_search._act_seed`, and the search's common-random-number salts come
from `eval_search`'s injective `_salt_base` / `_rollout_seed_base`. Those
derivations are IMPORTED rather than re-derived so the two tools cannot drift
into disagreeing about what a salt means.

NOTE (recorded trip hazard): `forksim.reseed_policy` is a silent no-op on a
policy with no generator, i.e. on a GREEDY `TorchPolicy`. The search's CRN
discipline — branch `j` of every candidate seeing the same rollout action
draws — would then reduce to "every rollout is deterministic", which is not
wrong but is a different (higher-variance-per-candidate-difference is gone,
but the rollouts stop exploring) measurement. This tool therefore always
loads the policy with `sample=True` and warns loudly if the loaded policy
exposes no generator. The behaviour policy's own actions never rely on
`reseed_policy`: they are drawn through `forksim.sample_from_prior` with an
explicit per-decision seed.

Usage:
    search_worker.py CKPT --bank runs/snapshots/BANK.jsonl \\
        --out runs/distill/v26_batch1/ --decisions 5000 --k 5 --m 8 \\
        --shard-size 4096 [--asc 10] [--room elite,boss] [--mass-cap 0.9] \\
        [--temperature 0.25] [--min-score-gap 0.05]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from sts2_rl import forksim
from sts2_rl.evaluation import load_torch_policy
from sts2_rl.forksim import CombatFork
from sts2_rl.run_env import STS2RunEnv, run_obs_layout
from sts2_rl.snapshots import act_module_for_encounter, load_snapshots
from tools import eval_search

#: Bumped whenever the on-disk shard layout changes, so a consumer can refuse
#: a stale shard set rather than reinterpreting arrays that mean something
#: else. Lives in the provenance JSON, not in the .npz: the archive holds the
#: five contract arrays and nothing else.
SHARD_SCHEMA = 1

#: The exact on-disk dtypes. The writer CASTS to these — the producer
#: accumulates in whatever the env hands it (obs `f` is float32, masks are
#: bool8 vectors) and the format, not the producer, decides storage.
SHARD_DTYPES = {
    "f": np.float16,
    "i": np.int32,
    "mask": np.bool_,
    "tgt_idx": np.int32,
    "tgt_p": np.float16,
}
SHARD_KEYS = tuple(SHARD_DTYPES)

#: Pad value for BOTH target arrays. Not a legal action id, not a probability.
PAD = -1

#: Rooms whose every decision is kept regardless of entropy.
HARD_ROOMS = ("ELITE", "BOSS")


# ════════════════════════════════════════════════════════════════════════════
# Shard IO — the producer/consumer contract
# ════════════════════════════════════════════════════════════════════════════


def write_shard(path, f, i, mask, tgt_idx, tgt_p) -> Path:
    """Write one shard of `n` records to `path` (an `.npz`).

    Every array is cast to its declared `SHARD_DTYPES` entry, so a caller may
    hand over float32 obs and uint8 masks without silently changing the
    format. Shapes are checked against each other: a ragged shard would read
    back as records whose obs and targets belong to different decisions,
    which no consumer could detect.

    Uncompressed `savez` on purpose: shards are written once and streamed
    many times, and the budget the plan sized (100k records ≈ 1.2 GB at
    f_dim 4736) is the uncompressed one.
    """
    arrays = {}
    for name, value in (("f", f), ("i", i), ("mask", mask),
                        ("tgt_idx", tgt_idx), ("tgt_p", tgt_p)):
        arr = np.asarray(value)
        if arr.ndim != 2:
            raise ValueError(f"write_shard: {name} must be 2-D (n, ...), got "
                             f"shape {arr.shape}")
        arrays[name] = arr.astype(SHARD_DTYPES[name], copy=False)
    n = arrays["f"].shape[0]
    for name, arr in arrays.items():
        if arr.shape[0] != n:
            raise ValueError(
                f"write_shard: ragged shard — f has {n} records but {name} "
                f"has {arr.shape[0]}")
    if arrays["tgt_idx"].shape != arrays["tgt_p"].shape:
        raise ValueError(
            f"write_shard: tgt_idx {arrays['tgt_idx'].shape} and tgt_p "
            f"{arrays['tgt_p'].shape} must have the same (n, k) shape")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        np.savez(fh, **arrays)
    return path


def shard_paths(path) -> "list[Path]":
    """The `.npz` files of a shard set, in filename order.

    Order is part of the contract: records are ordered WITHIN a shard, so an
    unsorted directory listing would make a training run's data order depend
    on the filesystem. Anything that is not an `.npz` (the provenance JSON,
    a stray log) is ignored.
    """
    path = Path(path)
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix == ".npz")
    return [path]


def iter_shards(path):
    """Yield each shard of a shard set (directory or single `.npz`) as a
    `{name: array}` dict, arrays materialized in their stored dtypes.

    `np.load` on an npz is lazy over a still-open file handle; this reads the
    arrays out and closes the archive, so a consumer can hold a shard after
    the iterator has moved on.
    """
    for shard in shard_paths(path):
        with np.load(shard) as data:
            missing = [k for k in SHARD_KEYS if k not in data]
            if missing:
                raise ValueError(f"{shard}: not a distill shard — missing {missing}")
            yield {k: np.asarray(data[k]) for k in SHARD_KEYS}


# ════════════════════════════════════════════════════════════════════════════
# Targets and selection — pure functions
# ════════════════════════════════════════════════════════════════════════════


def targets_from_scores(candidates, scores, k: int, temperature: float = 1.0):
    """`(tgt_idx, tgt_p)` for one decision: `(k,)` int32 and `(k,)` float16.

    `tgt_p` is the `--temperature` softmax of the candidates' MEAN rollout
    scores, renormalized over the candidates present — i.e. the search's own
    preference ordering kept as a distribution rather than collapsed to its
    argmax, so the distillation loss can learn "these two were nearly equal"
    instead of a hard label the search's m samples do not actually support.

    Temperature defaults to 1.0, which is what every pre-flag shard set was
    written at — and v26 is the argument for turning it down. Its rollout
    scores sat close enough together that T=1.0 produced near-uniform targets,
    a distribution carrying almost no preference to distil; the run learned
    its 5,004 shards and generalized negatively (the 08-28 diagnosis entry in
    `docs/superpowers/plans/v26-run-log.md`). T<1 divides the score gaps up
    before the exponential and sharpens the target toward the search's actual
    pick; T must be > 0 (T=0 is the argmax, not a softmax, and would divide by
    zero).

    The softmax is the max-subtracted one: rollout scores are returns plus a
    critic bootstrap and can be hundreds of points, whose bare `exp` overflows
    float64 into `inf/nan` and would poison a whole shard.

    Both arrays are padded to `k` with `PAD` (−1) — see the module docstring.
    """
    if not (float(temperature) > 0.0):
        raise ValueError(f"targets_from_scores: temperature must be > 0, "
                         f"got {temperature!r}")
    cand = [int(a) for a in candidates]
    s = np.asarray(scores, dtype=np.float64)
    if len(cand) != s.size:
        raise ValueError(f"targets_from_scores: {len(cand)} candidates but "
                         f"{s.size} scores")
    if len(cand) == 0:
        raise ValueError("targets_from_scores: no candidates")
    if len(cand) > k:
        raise ValueError(f"targets_from_scores: {len(cand)} candidates exceeds "
                         f"k={k} — the shard has no room for them")
    if not np.all(np.isfinite(s)):
        raise ValueError(f"targets_from_scores: non-finite scores {scores!r} "
                         f"(an unsearched decision must not be recorded)")
    e = np.exp((s - s.max()) / temperature)
    p = e / e.sum()

    idx = np.full(k, PAD, dtype=np.int32)
    prob = np.full(k, float(PAD), dtype=np.float16)
    idx[: len(cand)] = np.asarray(cand, dtype=np.int32)
    prob[: len(cand)] = p.astype(np.float16)
    return idx, prob


def score_gap(scores) -> float:
    """δ = top1 − top2 of the RAW mean rollout scores; `inf` for one candidate.

    Measured BEFORE any temperature, deliberately: this is the quantity the
    08-28 calibration showed to be the real blocker (median ≈ 0.016 return
    units, a fifth of records exactly tied), and it is invariant to whatever T
    the shard set is later written at, so two runs at different temperatures
    report the same decisiveness for the same decision.

    A lone candidate has no runner-up to be tied with — nothing for the filter
    to reject — so its gap is `inf` rather than 0. (In practice `expectimax`
    declines forced decisions upstream, but the boundary is worth pinning.)

    `np.partition` rather than a full sort: only the top two matter, and the
    tail can be arbitrarily spread without changing the answer.
    """
    s = np.asarray(scores, dtype=np.float64).ravel()
    if s.size == 0:
        raise ValueError("score_gap: no scores")
    if s.size == 1:
        return float("inf")
    top2 = np.partition(s, s.size - 2)[-2:]
    return float(abs(top2[1] - top2[0]))


def is_decisive(scores, min_gap: float) -> bool:
    """Does this searched decision clear `--min-score-gap`?

    `min_gap <= 0` disables the filter outright — including for EXACTLY tied
    scores, whose gap is 0. That asymmetry is the backward-compatibility
    contract: every shard set written before this flag existed kept its ties,
    and the default `G = 0.0` has to mean "unfiltered", not "drop the ties".

    Above zero the test is `δ > G`, strictly: δ == G is SKIPPED. v27's pinned
    rule reads "raw score gap > 0.05", and a boundary that quietly kept the
    equality case would admit exactly the records the filter is aimed at.
    """
    if not (float(min_gap) > 0.0):
        return True
    return bool(score_gap(scores) > float(min_gap))


def masked_entropy(probs, mask) -> float:
    """Shannon entropy (nats) of the policy distribution over the LEGAL
    actions only.

    `forksim.prior` already returns a masked softmax — illegal actions carry
    exactly zero mass — so restricting to `mask` changes nothing numerically
    and everything in intent: this is the same masked distribution the
    trainer's entropy bonus and `eval_search`'s argmax are computed on, not
    an entropy over the full 2000-wide action vector. A forced decision
    (one legal action) scores 0.
    """
    p = np.asarray(probs, dtype=np.float64)[np.asarray(mask, dtype=bool)]
    p = p[p > 0.0]
    if p.size == 0:
        return 0.0
    return float(-np.sum(p * np.log(p)))


def select_decisions(rooms, entropies) -> "list[bool]":
    """The selection rule, as a boolean per collected decision:

        keep = (room is ELITE or BOSS)  OR  (entropy > median of the batch)

    The median is over the whole batch — every decision this invocation
    collected, elite/boss included — so "top half of the batch" means exactly
    that. A strict `>` keeps the split honest when the entropies are degenerate
    (a batch of identical entropies selects nothing on entropy grounds rather
    than everything).

    Content-agnostic by construction: it reads a room TYPE and a number, never
    an encounter id.
    """
    rooms = list(rooms)
    ent = np.asarray(list(entropies), dtype=np.float64)
    if len(rooms) != ent.size:
        raise ValueError(f"select_decisions: {len(rooms)} rooms but {ent.size} "
                         f"entropies")
    if ent.size == 0:
        return []
    threshold = float(np.median(ent))
    return [(str(room).upper() in HARD_ROOMS) or (float(e) > threshold)
            for room, e in zip(rooms, ent)]


# ════════════════════════════════════════════════════════════════════════════
# Collection
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class Candidate:
    """One collected decision: enough to (a) apply the selection rule and
    (b) reproduce the exact state for the search. `prefix` is the action list
    from the fight's start — the forksim contract is that
    `fork.replay(prefix)` rebuilds this env byte-for-byte."""

    fight: int
    d: int
    snap_idx: int
    room: str
    entropy: float
    prefix: "tuple[int, ...]"
    f: np.ndarray            # float16 (f_dim,)
    i: np.ndarray            # int32   (i_dim,)
    mask: np.ndarray         # bool    (n_actions,)


@dataclass
class Stats:
    fights: int = 0
    decisions: int = 0
    forced: int = 0
    collected: int = 0
    #: Decisions `expectimax` actually searched — the GPU bill. Equals
    #: `searched + skipped_indecisive`; the difference between the two is what
    #: `--min-score-gap` costs.
    decisions_searched: int = 0
    #: Searched, then dropped by `--min-score-gap` (0 when the filter is off).
    skipped_indecisive: int = 0
    #: Records WRITTEN. The name predates the filter and is kept because
    #: `provenance["records"]` reads it.
    searched: int = 0
    flips: int = 0
    rollouts: int = 0
    unsearched_at_score: int = 0
    collect_seconds: float = 0.0
    search_seconds: float = 0.0
    room_hist: dict = field(default_factory=dict)


def collect_fight(fork: CombatFork, policy, fight: int, snap_idx: int,
                  room: str, *, device: str, stats: Stats) -> "list[Candidate]":
    """Play one fight under the deployed (sampling) policy, recording every
    non-forced combat decision.

    The live env is stepped forward while `prefix` accumulates the same
    actions — two views of one trajectory, exactly as `eval_search.play_fight`
    does it — so the scoring pass can rebuild any decision with one replay
    instead of the collection pass paying a replay per decision.
    """
    env = fork.replay([])
    prefix: list[int] = []
    out: list[Candidate] = []
    d = 0
    while d < eval_search.MAX_DECISIONS and CombatFork.in_combat(env):
        probs, mask = forksim.prior(policy, env)
        legal = int(np.count_nonzero(mask))
        if legal == 0:
            break
        stats.decisions += 1
        if legal < 2:
            # Forced: no choice to distil, and `expectimax` declines it.
            stats.forced += 1
        else:
            obs = env._build_obs()
            out.append(Candidate(
                fight=fight, d=d, snap_idx=snap_idx, room=room,
                entropy=masked_entropy(probs, mask),
                prefix=tuple(prefix),
                f=np.asarray(obs["f"], dtype=np.float16),
                i=np.asarray(obs["i"], dtype=np.int32),
                mask=np.asarray(mask, dtype=bool)))
        action = forksim.sample_from_prior(
            probs, eval_search._act_seed(fight, d), device=device)
        _obs, _r, terminated, truncated, _info = env.step(int(action))
        prefix.append(int(action))
        d += 1
        if terminated or truncated:
            break
    return out


# ════════════════════════════════════════════════════════════════════════════
# Driver
# ════════════════════════════════════════════════════════════════════════════


def _usable_snapshots(bank_path: str, rooms: "set[str] | None"):
    bank = load_snapshots(bank_path)
    snaps = [bank[i] for i in range(len(bank))]
    total = len(snaps)
    # Event-launched encounters have no act module, so `CombatFork` refuses
    # them; drop them with a count rather than crashing mid-run.
    dropped = [s for s in snaps if act_module_for_encounter(s.encounter_id) is None]
    snaps = [s for s in snaps if act_module_for_encounter(s.encounter_id) is not None]
    if rooms is not None:
        snaps = [s for s in snaps if s.room_type.upper() in rooms]
    return snaps, total, len(dropped)


def env_kwargs_for(args) -> dict:
    """The `STS2RunEnv` kwargs EVERY env in this run is built with — the
    measurement env and every `CombatFork` replay alike.

    One function so the two cannot drift. `card_obs` in particular MUST be
    threaded rather than left to the env's default: both modes have the same
    obs dims (4736/1533 at schema 13), so a mismatch between the mode the
    shards were actually written under and the mode stamped in
    `provenance.json` would be dimensionally invisible — a false obs-contract
    stamp in the very file that exists to catch a contract mismatch.
    """
    return {"ascension": args.asc, "card_obs": args.card_obs}


def load_policy(args, env):
    """`load_torch_policy` with this tool's fixed choices.

    `sample=True` unconditionally: the collection pass must walk the state
    distribution the DEPLOYED agent visits, and it is also what gives
    `forksim.reseed_policy` a generator to reset inside `expectimax` (see the
    module docstring's trip-hazard note). `card_obs` is passed explicitly —
    the loader's own default is `"hybrid"`, so omitting it would decode the
    checkpoint against a different card encoding than the env produces.
    """
    return load_torch_policy(args.ckpt, env_kind="run", env=env,
                             card_obs=args.card_obs, device=args.device,
                             sample=True, seed=0)


def run_worker(args) -> int:
    rooms = None
    if args.room:
        rooms = {r.strip().upper() for r in args.room.split(",") if r.strip()}
    snaps, total_loaded, n_dropped = _usable_snapshots(args.bank, rooms)
    if not snaps:
        print(f"search_worker: no usable snapshots in {args.bank} "
              f"(loaded {total_loaded}, rooms filter "
              f"{sorted(rooms) if rooms else 'none'})")
        return 2

    # ONE kwargs dict for every env this run builds — the measurement env and
    # every `CombatFork` replay alike. See `env_kwargs_for`.
    kwargs = env_kwargs_for(args)
    env0 = STS2RunEnv(**kwargs)
    policy, ckpt = load_policy(args, env0)
    if getattr(policy, "_generator", None) is None:
        print("WARNING: the loaded policy exposes no generator — "
              "forksim.reseed_policy is a NO-OP on it, so the search's "
              "common-random-number discipline is degenerate for this run.")

    # Obs dims come from the LAYOUT, never from magic constants. The env's own
    # space is asserted against it — but note that this assert is NOT a guard
    # on `--card-obs`: both modes ("hybrid", "features") happen to have the
    # identical 4736/1533 dims, so a mode mismatch is dimensionally invisible.
    # What makes the provenance stamp truthful is that the mode is threaded
    # into every env and into the policy load (`env_kwargs_for`, `load_policy`)
    # and then read back OFF THE ENV below, never off `args`.
    card_obs = str(env0._card_obs)
    layout = run_obs_layout(card_obs)
    f_dim, i_dim = int(layout.f_dim), int(layout.i_dim)
    if (env0.observation_space["f"].shape[0], env0.observation_space["i"].shape[0]) \
            != (f_dim, i_dim):
        raise RuntimeError(
            f"search_worker: env obs space "
            f"{(env0.observation_space['f'].shape[0], env0.observation_space['i'].shape[0])} "
            f"disagrees with run_obs_layout({card_obs!r}) {(f_dim, i_dim)}")
    n_actions = int(env0.action_space.n)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = Stats()
    print(f"ckpt {args.ckpt}")
    print(f"  schema {ckpt.get('obs_schema')}  arch {ckpt.get('arch')}  "
          f"card-obs {card_obs}  "
          f"f_dim {f_dim}  i_dim {i_dim}  n_actions {n_actions}")
    print(f"bank {args.bank}: {total_loaded} loaded, {len(snaps)} usable"
          f"{f', {n_dropped} event-launched dropped' if n_dropped else ''}"
          f"  filter {sorted(rooms) if rooms else 'none'}")
    print(f"asc {args.asc}  k {args.k}  m {args.m}  "
          f"mass-cap {args.mass_cap if args.mass_cap is not None else 'off'}  "
          f"gamma {args.gamma}  rollout-steps {args.rollout_steps}  "
          f"seed {args.seed}")
    print(f"temperature {args.temperature}  min-score-gap "
          f"{args.min_score_gap if args.min_score_gap > 0 else 'off'}")
    print(f"target {args.decisions} KEPT records  shard-size {args.shard_size}  "
          f"out {out_dir}")
    print()

    # ── the shard writer ───────────────────────────────────────────────────
    buf: "list[tuple]" = []
    shard_files: "list[str]" = []
    shard_index = 0

    def flush() -> None:
        nonlocal buf, shard_index
        if not buf:
            return
        path = write_shard(
            out_dir / f"shard-{shard_index:05d}.npz",
            np.stack([r[0] for r in buf]), np.stack([r[1] for r in buf]),
            np.stack([r[2] for r in buf]), np.stack([r[3] for r in buf]),
            np.stack([r[4] for r in buf]))
        shard_files.append(path.name)
        print(f"  wrote {path.name}  ({len(buf)} records)")
        shard_index += 1
        buf = []

    # ── the collect/score rounds ───────────────────────────────────────────
    # `--decisions` counts KEPT records, and `--min-score-gap` can reject a
    # decision only AFTER its rollouts are paid for, so one collect-then-score
    # pass no longer fills the budget. The driver runs ROUNDS: collect fights
    # until there are enough not-yet-scored SELECTED candidates to cover what
    # is still missing, score exactly those, and go round again if the filter
    # ate into the yield. With the filter off (G = 0.0) the first round covers
    # the whole budget and this degenerates to the original two passes.
    #
    # The selection median stays "over the WHOLE batch this invocation
    # collected": `pool` accumulates across rounds and `select_decisions` is
    # re-applied to all of it each time, so a later round's larger batch can
    # promote an earlier candidate that the then-median had excluded. `scored`
    # is what keeps a promoted-again candidate from being searched twice.
    #
    # TERMINATION (the thing the filter could plausibly break). `fight` is
    # monotonically increasing and is never rewound. The inner collect loop is
    # entered only while `fight < args.max_fights` and advances it by exactly
    # one per iteration, so it cannot spin; the outer loop carries the SAME
    # bound, so it can run at most `--max-fights` rounds. Every candidate the
    # score pass touches is added to `scored` BEFORE it is searched, so no
    # candidate can be re-offered whether it was kept, filtered out, or found
    # unsearchable. A bank whose every decision is indecisive therefore costs
    # `--max-fights` fights and then stops, short of `--decisions`, with a
    # provenance that says so (`skipped_indecisive`) — it does not loop.
    pool: "list[Candidate]" = []
    scored: "set[int]" = set()              # indices into `pool`
    forks: "dict[int, CombatFork]" = {}
    keep: "list[bool]" = []
    fight = 0
    round_no = 0

    while stats.searched < args.decisions and fight < args.max_fights:
        need = args.decisions - stats.searched
        round_no += 1

        # ── collect ────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        pending: "list[int]" = []
        while fight < args.max_fights:
            snap_idx = fight % len(snaps)
            snap = snaps[snap_idx]
            fork = CombatFork(snap,
                              seed=eval_search._fight_seed(args.seed, fight),
                              env_kwargs=kwargs)
            forks[fight] = fork
            got = collect_fight(fork, policy, fight, snap_idx,
                                snap.room_type, device=args.device, stats=stats)
            pool.extend(got)
            stats.fights += 1
            stats.room_hist[snap.room_type] = \
                stats.room_hist.get(snap.room_type, 0) + 1
            fight += 1
            keep = select_decisions([c.room for c in pool],
                                    [c.entropy for c in pool])
            pending = [j for j, k_ in enumerate(keep)
                       if k_ and j not in scored]
            print(f"collect fight {fight - 1:>4} snap {snap_idx:>3} "
                  f"{snap.room_type:<7} {snap.encounter_id:<26} "
                  f"+{len(got):>3} decisions -> pool {len(pool)}, "
                  f"pending {len(pending)}/{need} "
                  f"(kept {stats.searched}/{args.decisions})")
            if len(pending) >= need:
                break
        stats.collect_seconds += time.perf_counter() - t0
        stats.collected = len(pool)
        if not pending:
            # Only reachable with `--max-fights` exhausted (the inner loop has
            # no other exit that leaves `pending` short).
            break

        chosen = [pool[j] for j in pending[:need]]
        scored.update(pending[:need])
        entropies = np.asarray([c.entropy for c in pool])
        print()
        print(f"round {round_no}: pool {len(pool)} decisions over "
              f"{stats.fights} fights ({stats.forced} forced skipped); "
              f"entropy median {float(np.median(entropies)):.4f}, "
              f"mean {float(entropies.mean()):.4f}")
        print(f"selected {sum(keep)} of the pool -> scoring {len(chosen)} new")
        print()

        # ── score + write ──────────────────────────────────────────────────
        t0 = time.perf_counter()
        for n, cand in enumerate(chosen):
            fork = forks[cand.fight]
            res = forksim.expectimax(
                fork, list(cand.prefix), policy, args.k, args.m,
                salt_base=eval_search._salt_base(cand.fight, cand.d, args.m),
                rollout_seed_base=eval_search._rollout_seed_base(
                    cand.fight, cand.d, args.m),
                max_steps=args.rollout_steps, gamma=args.gamma,
                mass_cap=args.mass_cap)
            stats.rollouts += res.n_rollouts
            if not res.searched:
                # Only reachable if the replayed state disagrees with the
                # collected one about legality — a determinism break, worth
                # counting rather than silently writing a degenerate target.
                stats.unsearched_at_score += 1
                continue
            stats.decisions_searched += 1
            if not is_decisive(res.scores, args.min_score_gap):
                # The rollouts are already paid for; what the filter saves is
                # not GPU but the DILUTION of the target set. See the module
                # docstring's calibration numbers.
                stats.skipped_indecisive += 1
                continue
            stats.searched += 1
            # Flips are counted on KEPT records only, so `flips / records`
            # stays a rate over the shard set that was actually written.
            stats.flips += int(res.flipped)
            idx, prob = targets_from_scores(res.candidates, res.scores, args.k,
                                            temperature=args.temperature)
            buf.append((cand.f, cand.i, cand.mask, idx, prob))
            if len(buf) >= args.shard_size:
                flush()
            if (n + 1) % 25 == 0 or n + 1 == len(chosen):
                elapsed = time.perf_counter() - t0
                print(f"scored {n + 1}/{len(chosen)}  "
                      f"kept {stats.searched}/{args.decisions}  "
                      f"skipped {stats.skipped_indecisive}  "
                      f"flips {stats.flips}  rollouts {stats.rollouts}  "
                      f"{elapsed / (n + 1):.2f}s/decision")
            if stats.searched >= args.decisions:
                break
        stats.search_seconds += time.perf_counter() - t0

    flush()
    if not pool:
        print("search_worker: collected no non-forced decisions — nothing to do")
        return 2

    provenance = {
        "distill_schema": SHARD_SCHEMA,
        "ckpt": str(args.ckpt),
        "bank": str(args.bank),
        "k": args.k,
        "m": args.m,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Everything below is not required by the brief but is what makes a
        # shard set auditable later: the obs contract it was written against
        # (a shard set is meaningless under a different schema), the rest of
        # the search config, and the yield counters.
        "obs_schema": ckpt.get("obs_schema"),
        "arch": ckpt.get("arch"),
        # Read off the ENV, not off `args`: the stamp must describe what the
        # shards were actually written under (see the `card_obs` note above).
        "card_obs": card_obs,
        "f_dim": int(f_dim), "i_dim": int(i_dim), "n_actions": n_actions,
        "asc": args.asc, "room": args.room, "seed": args.seed,
        "gamma": args.gamma, "rollout_steps": args.rollout_steps,
        "mass_cap": args.mass_cap, "temperature": args.temperature,
        "min_score_gap": args.min_score_gap,
        "device": args.device,
        "decisions_requested": args.decisions,
        "shard_size": args.shard_size,
        "shards": shard_files,
        "records": stats.searched,
        "stats": {
            "fights": stats.fights, "decisions": stats.decisions,
            "forced": stats.forced, "collected": stats.collected,
            "selected": int(sum(keep)), "rounds": round_no,
            "decisions_searched": stats.decisions_searched,
            "skipped_indecisive": stats.skipped_indecisive,
            "searched": stats.searched,
            "flips": stats.flips, "rollouts": stats.rollouts,
            "unsearched_at_score": stats.unsearched_at_score,
            "collect_seconds": round(stats.collect_seconds, 3),
            "search_seconds": round(stats.search_seconds, 3),
            "room_hist": stats.room_hist,
        },
    }
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8")

    print()
    print("=" * 72)
    print(f"wrote {stats.searched} records in {len(shard_files)} shard(s) "
          f"to {out_dir}")
    if stats.searched < args.decisions:
        print(f"SHORT of the {args.decisions}-record budget after "
              f"{stats.fights} fights (--max-fights {args.max_fights}). "
              f"A bank whose decisions the search cannot separate cannot "
              f"fill a --min-score-gap {args.min_score_gap} budget; harvest "
              f"more snapshots or lower the gap.")
    print(f"flip rate {stats.flips}/{stats.searched} "
          f"({100.0 * stats.flips / stats.searched if stats.searched else float('nan'):.1f}%)"
          f"   rollouts {stats.rollouts}")
    print(f"decisiveness: searched {stats.decisions_searched}, "
          f"skipped {stats.skipped_indecisive} "
          f"(keep rate "
          f"{stats.searched / stats.decisions_searched if stats.decisions_searched else float('nan'):.3f}"
          f" at --min-score-gap {args.min_score_gap})")
    print(f"[timing] collect {stats.collect_seconds:.1f}s   "
          f"search {stats.search_seconds:.1f}s "
          f"({stats.search_seconds / stats.searched if stats.searched else float('nan'):.2f}s/decision)")
    print("A shard set is STALE the moment a newer generation's ckpt exists — "
          "regenerate into a fresh --out directory and repoint the trainer flag.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ckpt", help="checkpoint to search with (and to distil back into)")
    ap.add_argument("--bank", required=True, help="snapshot bank JSONL")
    ap.add_argument("--out", required=True, metavar="DIR",
                    help="output directory for the .npz shards + provenance.json")
    ap.add_argument("--decisions", type=int, default=5000,
                    help="how many searched decisions to WRITE, i.e. records "
                         "kept after --min-score-gap (default 5000)")
    ap.add_argument("--k", type=int, default=5, help="candidate actions per decision")
    ap.add_argument("--m", type=int, default=8, help="branches (salts) per candidate")
    ap.add_argument("--shard-size", type=int, default=4096,
                    help="records per .npz shard (default 4096)")
    ap.add_argument("--mass-cap", type=float, default=None,
                    help="adaptive breadth: shrink the candidate set to the "
                         "smallest prefix covering this prior mass "
                         "(clamped to [2, k]); default off = fixed k")
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="softmax temperature for the searched targets "
                         "(default 1.0 = the historical, pre-flag targets); "
                         "T<1 sharpens them toward the search's pick")
    ap.add_argument("--min-score-gap", type=float, default=0.0, metavar="G",
                    help="DECISIVENESS FILTER: drop a searched decision whose "
                         "raw top1-top2 rollout-score gap is <= G (default 0.0 "
                         "= no filter, exact ties kept = pre-flag behaviour). "
                         "--decisions then counts KEPT records. v27 uses 0.05: "
                         "temperature alone could not sharpen near-tied scores "
                         "(19.5%% exactly equal); G=0.05 keeps ~41%% and lifts "
                         "the median target gap to 0.317 at T=0.25 (see "
                         "docs/superpowers/plans/v27-run-log.md, 08-28)")
    ap.add_argument("--asc", type=int, default=10, help="ascension the drill env runs at")
    ap.add_argument("--room", default=None,
                    help="comma-separated room types to keep from the BANK, e.g. "
                         "elite,boss (default: every room type in the bank). "
                         "Distinct from the selection rule, which keeps every "
                         "elite/boss decision it walks")
    ap.add_argument("--max-fights", type=int, default=10000,
                    help="hard cap on collection fights, so a bank that yields "
                         "few decisions cannot loop forever")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rollout-steps", type=int, default=120,
                    help="max steps in a search rollout (forksim default 120)")
    ap.add_argument("--gamma", type=float, default=0.999)
    ap.add_argument("--card-obs", default="hybrid", choices=("hybrid", "features"),
                    help="card encoding for the drill env AND the policy load; "
                         "both modes share the same obs dims, so a mismatch is "
                         "dimensionally invisible — it is threaded, not asserted")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)
    if args.decisions < 1:
        ap.error("--decisions must be >= 1")
    if args.shard_size < 1:
        ap.error("--shard-size must be >= 1")
    if args.min_score_gap < 0.0:
        # A negative gap is not "even less filtering" — 0.0 is already the
        # off switch — so it can only be a typo (or a lost minus sign) worth
        # refusing before hours of GPU go into a set nobody meant to ask for.
        ap.error("--min-score-gap must be >= 0 (0 = no filter)")
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
