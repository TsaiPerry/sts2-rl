"""Vectorized env stepping for ``train_torch.py`` — in-process or subprocess.

The trainer steps ``--n-envs`` envs per timestep. Model inference is already
batched across them; env stepping is pure Python and single-core, and this
module can hand whole envs to worker *processes* to parallelize it.

**It is off by default, and usually should be** — see
:func:`resolve_n_workers` for the numbers. Env stepping is a small slice of an
iteration, so parallelizing it moves the needle ~4%. The machinery is here
because the profile will shift, not because it currently pays.

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


def build_env(spec: EnvSpec):
    """The single env factory — used by the serial path and by every worker."""
    acts = list(spec.acts) if spec.acts is not None else None
    if spec.kind == "column":
        from sts2_rl.curriculum_env import STS2CurriculumRunEnv

        # Floor-only reward defaults live on the env classes; win_hp_bonus
        # is deliberately not passed to either run-scale env (it is HP
        # shaping).
        return STS2CurriculumRunEnv(
            acts=acts, card_obs=spec.card_obs,
            branch_prob=spec.branch_prob,
        )
    if spec.kind == "run":
        from sts2_rl.run_env import STS2RunEnv

        return STS2RunEnv(acts=acts, card_obs=spec.card_obs)
    if spec.kind != "combat":
        raise ValueError(f"unknown env kind {spec.kind!r}")

    from sts2_rl.full_env import STS2FullCombatEnv
    from sts2_rl.monsters.overgrowth import ENCOUNTERS

    return STS2FullCombatEnv(
        encounter=ENCOUNTERS[spec.encounter] if spec.encounter else None,
        card_obs=spec.card_obs,
        enemy_hp_reward_scale=spec.enemy_hp_reward,
        win_hp_bonus=spec.win_hp_bonus,
    )


# ── one step's worth of batched results ───────────────────────────────────

class StepBatch(NamedTuple):
    obs: TensorObs                     # (E, f_dim)/(E, i_dim) halves, post-auto-reset
    rewards: np.ndarray                # (E,) float32, raw env reward
    terminated: np.ndarray             # (E,) bool
    truncated: np.ndarray              # (E,) bool
    masks: np.ndarray                  # (E, n_actions) bool, for `obs`
    successes: np.ndarray              # (E,) bool, info["is_success"] on done
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
                o, _ = env.reset()
            f[idx] = o["f"]
            i[idx] = o["i"]
            masks[idx] = env.action_masks()
        return StepBatch(TensorObs(f, i), rewards, terminated, truncated, masks,
                         successes, final_obs)

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

def resolve_n_workers(n_envs: int, requested: int) -> int:
    """``--n-workers``: 0 = in-process (the default), N = that many processes.

    Workers default OFF because they don't pay for themselves: profiled
    2026-07-18, env stepping is ~15% of an iteration (act-time inference 46%,
    PPO update 39%), and 8 workers parallelize it only 1.51× — pipe transport
    of the 117 KB observation eats the rest. That is ~4% end-to-end, against a
    3.3s spawn cost and one engine copy per worker. Reach for this when the
    balance shifts (cheaper inference, or much more expensive envs) — and
    re-measure rather than assuming.
    """
    if requested < 0:
        raise ValueError("--n-workers cannot be negative")
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
