"""Vectorized env stepping for ``train_torch.py`` — in-process or subprocess.

The trainer steps ``--n-envs`` envs per timestep. Model inference is already
batched across them; env stepping is pure Python and single-core, and this
module can hand whole envs to worker *processes* to parallelize it.

**It is on by default at scale** — ``--n-workers -1`` (auto) resolves to
:data:`AUTO_N_WORKERS` subprocess workers at :data:`AUTO_WORKER_MIN_ENVS`+
envs and stays serial below that; see :func:`resolve_n_workers` for the
2026-08-02 numbers (+57% sps combat / +42% column at 32 envs). The old
"~4%, leave off" verdict predates the integer obs schema and is dead.

Two implementations behind one interface:

- :class:`SerialVecEnv` — the historical in-process loop, kept as the
  debugging path and as the reference the equivalence test compares against.
- :class:`SubprocVecEnv` — ``multiprocessing`` workers (``spawn``, the only
  start method on Windows), each owning a contiguous block of envs.

Both delegate to the same :class:`_EnvGroup`, so there is exactly one
implementation of reset/step/auto-reset semantics and the two paths cannot
drift. Env *i* (global index) is seeded and stepped identically regardless of
how many workers there are: envs each own a ``random.Random``, nothing is
shared, and the split is a runtime detail — a fixed seed and a fixed policy
produce identical rollouts on either path.

Semantics worth knowing:

- **Auto-reset**: when an episode ends the group resets that env and returns
  the *reset* observation (and its mask) in ``obs``/``masks``, gymnasium's
  vector convention. ``terminated``/``truncated`` are reported separately.
- **``final_obs``** carries the terminal observation for **truncated**
  episodes only — the trainer needs it for the time-limit bootstrap
  (``gamma * V(final_obs)``). A natural termination bootstraps 0, so shipping
  its final obs would be ~117 KB of pure transport waste per event.
"""
from __future__ import annotations

import multiprocessing as mp
import traceback
from dataclasses import dataclass
from typing import Any, NamedTuple, Sequence

import numpy as np

from sts2_rl.tensor_obs import TensorObs


# ── env construction ──────────────────────────────────────────────────────
# Everything a worker needs to build its own envs, as one frozen (picklable,
# spawn-safe) value. Env objects themselves never cross a process boundary.

@dataclass(frozen=True)
class EnvSpec:
    """The trainer's ``--env``/env-flag choices, in picklable form."""

    kind: str = "combat"                      # combat | run | column
    acts: tuple[str, ...] | None = None       # run/column only
    card_obs: str = "hybrid"
    encounter: str | None = None              # combat only
    enemy_hp_reward: float = 0.0              # combat only
    win_hp_bonus: float = 1.0                 # combat only
    branch_prob: float = 0.0                  # column only: anneal knob
    ascension: int = 0                        # all env kinds: the run-scale
                                               # envs took it in Phase A
                                               # (Tasks 1-5); the combat env
                                               # since v7 Task 10 (gimmick
                                               # probes fight at the stage's
                                               # ascension).
    # v24 (Task 1): per-episode ascension re-roll, uniform [lo, hi] at each
    # reset (run-scale envs only). Tuple, not list, so the spec stays
    # hashable/picklable like the other tuple knobs above. None = default =
    # fixed `ascension` above, bit-identical env.
    ascension_sample: "tuple[int, int] | None" = None
    # v7 reward/curriculum knobs (run/column only, plan Task 7). All default
    # OFF so a default spec builds a bit-identical env. reward_win_run is
    # None (not a float) so "unset" keeps the env's own reward_win default.
    floor_rewards_by_act: tuple[float, ...] | None = None
    reward_win_run: float | None = None
    reward_upgrade: float = 0.0
    reward_remove: float = 0.0
    reward_elite: float = 0.0
    reward_relic: float = 0.0
    # v11 (plan 2026-08-14-v11-combat-detour Task 2): +reward_boss per act
    # boss defeated; the final win pays reward_win + reward_boss. 0.0 = the
    # env's own default, so a default spec stays bit-identical.
    reward_boss: float = 0.0
    # v11.1: +reward_elite_attempt once per elite room entered (win or
    # lose) — reward_elite pays only on the rewards screen. 0.0 = default.
    reward_elite_attempt: float = 0.0
    # v24: per-act elite pay (0-based act_index), replacing the two flat
    # scalars above when set. Tuples, not lists, so the spec stays
    # hashable/picklable like floor_rewards_by_act. None = flat = default.
    elite_rewards_by_act: tuple[float, ...] | None = None
    elite_attempt_rewards_by_act: tuple[float, ...] | None = None
    # v24: within-act elite kill escalator -- N-th kill pays
    # base*(1+esc*(N-1)), reset on act advance. 0.0 = default (inert).
    reward_elite_escalator: float = 0.0
    # v8 curriculum mask (plan Task 4, run/column only): None keeps the
    # env's own default (no masking) — see `build_env`'s v7_kwargs below,
    # same "only set when not None" pattern as reward_win_run.
    rest_heal_mask_above: float | None = None
    # v8 HP-economy / potion-ledger knobs (plan Tasks 1-2, run/column only).
    # Both default OFF (0.0) so a default spec builds a bit-identical env,
    # same as the other v7/v8 reward knobs above.
    hp_potential_scale: float = 0.0
    potion_potential_scale: float = 0.0
    deck_random_prob: float = 0.0
    # v9 reward fixes (plan 2026-08-12-v9-rest-potion-fix), both default OFF.
    rest_heal_shaping_knee_cap: bool = False
    potion_death_expiry: bool = False
    potion_death_penalty: float = 0.0
    # v16 (plan Task 2): flat penalty per unspent energy point at every
    # player-turn end. Defaults OFF (0.0), same bit-identical-by-default
    # contract as the other v7/v8/v9 reward knobs above.
    energy_waste_penalty: float = 0.0
    # v21 (spec 2026-08-22-v21-potion-option-value-design): -k * v(s) per
    # drink + optional death expiry. Defaults OFF = bit-identical env.
    potion_option_value: float = 0.0
    potion_option_expiry: bool = False
    # v24: partial refund of the ledger's release charge for an elite/boss
    # in-combat drink (non-AnyTime potion). Default OFF = bit-identical env.
    potion_timing_refund: float = 0.0
    # v10 (plan 2026-08-13-v10-escape-and-settle Task 1): share of the HP
    # potential below the knee. 0.7 = the env's own default, so a default
    # spec stays bit-identical; the s11-lowshare contingency rung runs 0.8.
    hp_potential_low_share: float = 0.7
    # v14 (mechanics-exposure plan Task 5): a JSON packages file (card-id
    # lists appended whole to the starting deck) and its per-episode
    # injection probability. deck_inject=None / prob 0.0 = the env's own
    # default, so a default spec stays bit-identical (run/column only).
    deck_inject: str | None = None
    deck_inject_prob: float = 0.0
    # v15 (extension-exposure plan Task 1): mid-run twin of deck_inject --
    # a JSON packages file appended to the LIVE deck on a floor advance
    # instead of the starting deck. Same bit-identical-by-default contract.
    deck_inject_midrun: str | None = None
    deck_inject_midrun_prob: float = 0.0
    # combat only (phase-3 Task 3, R11): a snapshot dataset PATH (never a
    # live SnapshotDataset -- this whole dataclass must stay picklable, and
    # a SnapshotDataset carries live Card/Relic instances). Each
    # SubprocVecEnv worker loads it independently, process-locally, the
    # first time it builds an env (STS2FullCombatEnv's own lazy-load).
    start_snapshots: str | None = None
    # v20 (Task 3b): non-refundable boss-fight HP-loss price. Default OFF.
    boss_hp_loss_penalty: float = 0.0
    # v20 drill mode (run env only): schema-2 bank path + per-reset drill
    # probability + stratified pool masses + within-pool encounter weights.
    # Tuples-of-pairs, not dicts, so the spec stays hashable/picklable like
    # floor_rewards_by_act; build_env dict()s them. All defaults = OFF =
    # bit-identical env.
    drill_snapshots: str | None = None
    drill_prob: float = 0.0
    drill_pools: "tuple[tuple[str, float], ...] | None" = None
    drill_encounter_weights: "tuple[tuple[str, float], ...] | None" = None


def build_env(spec: EnvSpec):
    """The single env factory — used by the serial path and by every worker."""
    acts = list(spec.acts) if spec.acts is not None else None
    # v7 knobs, shared by both run-scale envs. deck_random_prob is passed
    # only when opted in (the kwarg lands with Task 9's env support; 0.0 is
    # fully inert either way), and reward_win_run only when set so the
    # env's own reward_win default (3.0) stays authoritative.
    v7_kwargs: dict = dict(
        ascension_sample=spec.ascension_sample,
        floor_rewards_by_act=spec.floor_rewards_by_act,
        reward_upgrade=spec.reward_upgrade,
        reward_remove=spec.reward_remove,
        reward_elite=spec.reward_elite,
        reward_relic=spec.reward_relic,
        reward_boss=spec.reward_boss,
        reward_elite_attempt=spec.reward_elite_attempt,
        elite_rewards_by_act=spec.elite_rewards_by_act,
        elite_attempt_rewards_by_act=spec.elite_attempt_rewards_by_act,
        reward_elite_escalator=spec.reward_elite_escalator,
        hp_potential_scale=spec.hp_potential_scale,
        hp_potential_low_share=spec.hp_potential_low_share,
        potion_potential_scale=spec.potion_potential_scale,
        potion_death_penalty=spec.potion_death_penalty,
        energy_waste_penalty=spec.energy_waste_penalty,
        potion_option_value=spec.potion_option_value,
        potion_option_expiry=spec.potion_option_expiry,
        potion_timing_refund=spec.potion_timing_refund,
        deck_inject=spec.deck_inject,
        deck_inject_prob=spec.deck_inject_prob,
        deck_inject_midrun=spec.deck_inject_midrun,
        deck_inject_midrun_prob=spec.deck_inject_midrun_prob,
    )
    if spec.reward_win_run is not None:
        v7_kwargs["reward_win"] = spec.reward_win_run
    if spec.rest_heal_mask_above is not None:
        v7_kwargs["rest_heal_mask_above"] = spec.rest_heal_mask_above
    if spec.deck_random_prob:
        v7_kwargs["deck_random_prob"] = spec.deck_random_prob
    if spec.rest_heal_shaping_knee_cap:
        v7_kwargs["rest_heal_shaping_knee_cap"] = True
    if spec.potion_death_expiry:
        v7_kwargs["potion_death_expiry"] = True
    if spec.kind == "column":
        from sts2_rl.curriculum_env import STS2CurriculumRunEnv

        # Floor-only reward defaults live on the env classes; win_hp_bonus
        # is deliberately not passed to either run-scale env (it is HP
        # shaping).
        return STS2CurriculumRunEnv(
            acts=acts, card_obs=spec.card_obs,
            branch_prob=spec.branch_prob,
            ascension=spec.ascension,
            **v7_kwargs,
        )
    if spec.kind == "run":
        from sts2_rl.run_env import STS2RunEnv

        # v20 knobs are run-env only (the column env has no drill mode and
        # no boss-combat context); passed only when opted in so a default
        # spec builds a byte-identical env.
        run_kwargs: dict = {}
        if spec.boss_hp_loss_penalty:
            run_kwargs["boss_hp_loss_penalty"] = spec.boss_hp_loss_penalty
        if spec.drill_snapshots is not None:
            run_kwargs.update(
                drill_snapshots=spec.drill_snapshots,
                drill_prob=spec.drill_prob,
                drill_pools=(dict(spec.drill_pools)
                             if spec.drill_pools is not None else None),
                drill_encounter_weights=(
                    dict(spec.drill_encounter_weights)
                    if spec.drill_encounter_weights is not None else None),
            )
        return STS2RunEnv(acts=acts, card_obs=spec.card_obs,
                          ascension=spec.ascension, **v7_kwargs, **run_kwargs)
    if spec.kind != "combat":
        raise ValueError(f"unknown env kind {spec.kind!r}")

    from sts2_rl.full_env import STS2FullCombatEnv
    from sts2_rl.monsters.overgrowth import ENCOUNTERS

    return STS2FullCombatEnv(
        encounter=ENCOUNTERS[spec.encounter] if spec.encounter else None,
        card_obs=spec.card_obs,
        enemy_hp_reward_scale=spec.enemy_hp_reward,
        win_hp_bonus=spec.win_hp_bonus,
        snapshots=spec.start_snapshots,
        ascension=spec.ascension,
    )


# ── one step's worth of batched results ───────────────────────────────────

#: Per-episode behavior tallies the run-scale envs report in `info` on their
#: terminal step (run_env `_count_behavior`). Column order of
#: `StepBatch.metrics`.
EP_METRIC_KEYS = (
    "ep_end_turns", "ep_energy_unspent", "ep_card_offers", "ep_card_takes",
    # v7 (plan Task 7): behavior counters from run_env's Task-6 tallies.
    "ep_upgrades", "ep_removes", "ep_elites_won",
    "ep_potions_obtained", "ep_potions_used",
    # v8 (plan Task 2): potion ledger USE classification + timing.
    "ep_potions_used_elite", "ep_potions_used_boss", "ep_potions_used_normal",
    "ep_potions_expired", "ep_potion_use_hp",
    # v8 (plan Task 3): relics gained tally.
    "ep_relics",
    # v8 (plan Task 1): combat sloppiness tally, independent of whether
    # hp_potential_scale shaping is on. Appended at the END (plan Task 5) —
    # column order is a public contract (train_torch/tests index into it).
    "ep_hp_lost",
    # v20 (Task 3b): HP lost inside BOSS combats only — the boss-hp-loss
    # term's instrument. Inserted BEFORE "floor" so metrics[:, -1] stays the
    # floor column (train_torch.py:910 indexes it as -1).
    "ep_boss_hp_lost",
    # v23: voluntary out-of-combat discards (the v22 affordance) — gives the
    # training CSV mid-run visibility of the discard rate instead of only the
    # final eval. Inserted BEFORE "floor" like ep_boss_hp_lost above.
    "ep_potions_discarded",
    # The floor the episode ended on -- run_env's `info["floor"]`, which is
    # present every step but only harvested here on the terminal one, so it
    # reads as "floors completed". train_torch logs it as ep_ret (the combat
    # env reports no floor, so it falls back to raw return there).
    "floor")


class StepBatch(NamedTuple):
    obs: TensorObs                     # (E, f_dim)/(E, i_dim) halves, post-auto-reset
    rewards: np.ndarray                # (E,) float32, raw env reward
    terminated: np.ndarray             # (E,) bool
    truncated: np.ndarray              # (E,) bool
    masks: np.ndarray                  # (E, n_actions) bool, for `obs`
    successes: np.ndarray              # (E,) bool, info["is_success"] on done
    metrics: np.ndarray                # (E, len(EP_METRIC_KEYS)) float32; NaN
                                       # except done envs that reported them
                                       # (the combat env reports none)
    final_obs: dict[int, TensorObs]    # truncated envs only (see module docs)


# ── the shared implementation ─────────────────────────────────────────────

class _EnvGroup:
    """A contiguous block of envs, stepped in lockstep. Process-agnostic."""

    def __init__(self, spec: EnvSpec, n_envs: int) -> None:
        self.envs = [build_env(spec) for _ in range(n_envs)]
        obs_space = self.envs[0].observation_space
        self.f_dim = int(obs_space["f"].shape[0])
        self.i_dim = int(obs_space["i"].shape[0])
        self.obs_dim = (self.f_dim, self.i_dim)
        self.n_actions = int(self.envs[0].action_space.n)

    def reset(self, seeds: Sequence[int | None]) -> tuple[TensorObs, np.ndarray]:
        f = np.empty((len(self.envs), self.f_dim), np.float32)
        i = np.empty((len(self.envs), self.i_dim), np.int32)
        masks = np.empty((len(self.envs), self.n_actions), bool)
        for idx, (env, seed) in enumerate(zip(self.envs, seeds)):
            o, _ = env.reset(seed=None if seed is None else int(seed))
            f[idx] = o["f"]
            i[idx] = o["i"]
            masks[idx] = env.action_masks()
        return TensorObs(f, i), masks

    def step(self, actions: Sequence[int]) -> StepBatch:
        n = len(self.envs)
        f = np.empty((n, self.f_dim), np.float32)
        i = np.empty((n, self.i_dim), np.int32)
        masks = np.empty((n, self.n_actions), bool)
        rewards = np.empty(n, np.float32)
        terminated = np.zeros(n, bool)
        truncated = np.zeros(n, bool)
        successes = np.zeros(n, bool)
        metrics = np.full((n, len(EP_METRIC_KEYS)), np.nan, np.float32)
        final_obs: dict[int, TensorObs] = {}
        for idx, env in enumerate(self.envs):
            o, r, term, trunc, info = env.step(int(actions[idx]))
            rewards[idx] = r
            terminated[idx] = term
            truncated[idx] = trunc
            if trunc and not term:
                final_obs[idx] = TensorObs(
                    np.asarray(o["f"], np.float32).copy(),
                    np.asarray(o["i"], np.int32).copy())
            if term or trunc:
                successes[idx] = bool(info.get("is_success"))
                for k, key in enumerate(EP_METRIC_KEYS):
                    v = info.get(key)
                    if v is not None:
                        metrics[idx, k] = float(v)
                o, _ = env.reset()
            f[idx] = o["f"]
            i[idx] = o["i"]
            masks[idx] = env.action_masks()
        return StepBatch(TensorObs(f, i), rewards, terminated, truncated, masks,
                         successes, metrics, final_obs)

    def close(self) -> None:
        for env in self.envs:
            env.close()


# ── in-process path ───────────────────────────────────────────────────────

class SerialVecEnv:
    """The original single-core loop. Same interface as SubprocVecEnv."""

    def __init__(self, spec: EnvSpec, n_envs: int) -> None:
        self.num_envs = n_envs
        self.n_workers = 0
        self._group = _EnvGroup(spec, n_envs)
        self.obs_dim = self._group.obs_dim
        self.n_actions = self._group.n_actions

    def reset(self, seeds: Sequence[int | None]) -> tuple[TensorObs, np.ndarray]:
        return self._group.reset(seeds)

    def step(self, actions: Sequence[int]) -> StepBatch:
        return self._group.step(actions)

    def close(self) -> None:
        self._group.close()


# ── worker path ───────────────────────────────────────────────────────────

def _worker_main(conn, spec: EnvSpec, n_envs: int) -> None:
    """Worker entry point. Module-level so ``spawn`` can pickle it by name."""
    group = None
    try:
        group = _EnvGroup(spec, n_envs)
        conn.send(("ready", (group.obs_dim, group.n_actions)))
        while True:
            cmd, payload = conn.recv()
            if cmd == "close":
                break
            if cmd == "reset":
                conn.send(("ok", group.reset(payload)))
            elif cmd == "step":
                conn.send(("ok", group.step(payload)))
            else:  # pragma: no cover - protocol violation
                raise AssertionError(f"unknown command {cmd!r}")
    except (KeyboardInterrupt, EOFError):
        pass                              # parent went away / Ctrl-C: just exit
    except BaseException:
        # Without this the parent blocks forever on recv() instead of showing
        # the worker's traceback.
        try:
            conn.send(("error", traceback.format_exc()))
        except BaseException:
            pass
    finally:
        if group is not None:
            group.close()
        conn.close()


def _split(n_envs: int, n_workers: int) -> list[int]:
    """Envs per worker, as evenly as possible (extras go to the first ones)."""
    base, extra = divmod(n_envs, n_workers)
    return [base + (1 if i < extra else 0) for i in range(n_workers)]


class SubprocVecEnv:
    """Steps envs in ``n_workers`` spawned processes, lockstep-synchronous.

    Each worker owns whole envs, which is what makes the run-scale envs safe
    here: their engine runs on a greenlet, and greenlets are per-process state
    that never crosses the pipe.
    """

    def __init__(self, spec: EnvSpec, n_envs: int, n_workers: int) -> None:
        if not 1 <= n_workers <= n_envs:
            raise ValueError(f"n_workers must be in 1..{n_envs}, got {n_workers}")
        self.num_envs = n_envs
        self.n_workers = n_workers
        self.counts = _split(n_envs, n_workers)

        starts = np.cumsum([0] + self.counts)
        self._slices = [slice(int(a), int(b)) for a, b in zip(starts, starts[1:])]

        ctx = mp.get_context("spawn")
        self._conns: list[Any] = []
        self._procs: list[Any] = []
        self._closed = False
        for w, count in enumerate(self.counts):
            parent_conn, child_conn = ctx.Pipe()
            proc = ctx.Process(target=_worker_main, args=(child_conn, spec, count),
                               name=f"sts2-env-{w}", daemon=True)
            proc.start()
            child_conn.close()            # parent keeps only its own end
            self._conns.append(parent_conn)
            self._procs.append(proc)

        # Handshake: workers report their spaces once their envs exist, so the
        # parent never has to build an env of its own.
        dims = {self._recv(conn) for conn in self._conns}
        if len(dims) != 1:  # pragma: no cover - would mean divergent env specs
            self.close()
            raise RuntimeError(f"workers disagree on env spaces: {dims}")
        self.obs_dim, self.n_actions = dims.pop()

    # -- protocol ---------------------------------------------------------

    def _recv(self, conn):
        tag, payload = conn.recv()
        if tag == "error":
            self.close()
            raise RuntimeError(f"env worker failed:\n{payload}")
        return payload

    def _scatter_gather(self, cmd: str, parts: list) -> list:
        # Send to every worker before reading any reply — that overlap is the
        # whole point of this class.
        for conn, part in zip(self._conns, parts):
            conn.send((cmd, part))
        return [self._recv(conn) for conn in self._conns]

    # -- interface --------------------------------------------------------

    def reset(self, seeds: Sequence[int | None]) -> tuple[TensorObs, np.ndarray]:
        seeds = list(seeds)
        results = self._scatter_gather("reset", [seeds[sl] for sl in self._slices])
        obs = TensorObs(
            np.concatenate([o.f for o, _ in results]),
            np.concatenate([o.i for o, _ in results]),
        )
        return obs, np.concatenate([m for _, m in results])

    def step(self, actions: Sequence[int]) -> StepBatch:
        actions = np.asarray(actions)
        batches = self._scatter_gather("step", [actions[sl] for sl in self._slices])
        final_obs: dict[int, TensorObs] = {}
        for sl, batch in zip(self._slices, batches):
            for i, obs in batch.final_obs.items():
                final_obs[sl.start + i] = obs
        return StepBatch(
            obs=TensorObs(
                np.concatenate([b.obs.f for b in batches]),
                np.concatenate([b.obs.i for b in batches]),
            ),
            rewards=np.concatenate([b.rewards for b in batches]),
            terminated=np.concatenate([b.terminated for b in batches]),
            truncated=np.concatenate([b.truncated for b in batches]),
            masks=np.concatenate([b.masks for b in batches]),
            successes=np.concatenate([b.successes for b in batches]),
            metrics=np.concatenate([b.metrics for b in batches]),
            final_obs=final_obs,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for conn in self._conns:
            try:
                conn.send(("close", None))
            except (BrokenPipeError, OSError):
                pass
        for conn, proc in zip(self._conns, self._procs):
            try:
                conn.close()
            except OSError:
                pass
            proc.join(timeout=5)
            if proc.is_alive():           # wedged worker: don't orphan it
                proc.terminate()
                proc.join(timeout=5)


# ── selection ─────────────────────────────────────────────────────────────

#: ``resolve_n_workers`` auto mode picks this many workers for
#: training-scale runs (measured optimum of the arms tried; see docstring).
AUTO_N_WORKERS = 4

#: Auto mode stays serial below this many envs: tiny runs (smoke tests,
#: probes) would pay the ~3s spawn cost and one engine copy per worker for
#: seconds of stepping.
AUTO_WORKER_MIN_ENVS = 16


def resolve_n_workers(n_envs: int, requested: int) -> int:
    """``--n-workers``: -1 = auto (the default), 0 = in-process, N = N procs.

    Workers used to default OFF on the strength of a 2026-07-18 profile
    (117 KB float observations, env stepping ~15% of an iteration, workers
    worth ~4% end-to-end). Both inputs died: the integer schema cut the
    payload to ~9 KB (combat) / ~25 KB (run), and the obs builders were
    vectorized. Re-measured 2026-08-02 (RTX 3070, cuda, entset, 32 envs,
    paired seeds 1/2/3, identical win rates across arms): combat 522 -> 818
    sps with 4 workers (+57%), column 319 -> 453 (+42%); at 8 envs the win
    shrinks to ~+18%. Auto therefore uses ``AUTO_N_WORKERS`` processes at
    ``AUTO_WORKER_MIN_ENVS``+ envs and stays serial below that, where spawn
    cost and per-worker engine copies outweigh seconds of stepping.
    """
    if requested == -1:
        requested = AUTO_N_WORKERS if n_envs >= AUTO_WORKER_MIN_ENVS else 0
    if requested < 0:
        raise ValueError("--n-workers must be -1 (auto), 0 (serial), or > 0")
    return min(requested, n_envs)


def make_vec_env(spec: EnvSpec, n_envs: int, n_workers: int):
    """SerialVecEnv for ``n_workers <= 1``, SubprocVecEnv otherwise.

    One worker is *not* worth a process: it moves the same serial stepping
    behind a pipe and adds a copy per step. Ask for it explicitly by
    constructing SubprocVecEnv (the equivalence test does).
    """
    if n_workers <= 1:
        return SerialVecEnv(spec, n_envs)
    return SubprocVecEnv(spec, n_envs, n_workers)
