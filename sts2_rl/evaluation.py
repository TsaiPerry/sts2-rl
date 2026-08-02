"""Policy evaluation — win rate and lethal-probe accuracy side by side.

OBS_PLAN Phase 4 (steps 11–12): probe accuracy is a first-class metric next to
win rate, and the same evaluators drive the full-vs-ablated observation
ablation. CLIs: ``py eval.py --env full`` and ``py test/ablation.py``.

A *policy* here is any callable ``(env, obs, mask) -> action int`` —
``masked_random_policy`` / ``model_policy`` are the adapters, and
``probes.lethal_oracle`` is the scripted reference player.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

from .full_env import STS2FullCombatEnv, numeric_obs_indices
from .probes import Probe, ProbeResult, probe_accuracy, run_probes

Policy = Callable[..., int]


# ── Policy adapters ───────────────────────────────────────────────────────────


def masked_random_policy(seed: int = 0) -> Policy:
    """Uniform over legal actions — the floor every trained policy must beat."""
    rng = np.random.default_rng(seed)

    def _policy(env: Any, obs: np.ndarray, mask: np.ndarray) -> int:
        return int(rng.choice(np.flatnonzero(mask)))

    return _policy


def model_policy(
    model: Any,
    obs_transform: Callable[[np.ndarray], np.ndarray] | None = None,
) -> Policy:
    """Adapt an sb3-contrib MaskablePPO model (deterministic predictions).

    ``obs_transform`` preprocesses the observation before the model sees it —
    pass ``ablation_transform()`` when a model *trained* on ``AblatedObsEnv``
    observations is evaluated against a raw env (the probe suite always hands
    out raw observations)."""

    def _policy(env: Any, obs: np.ndarray, mask: np.ndarray) -> int:
        if obs_transform is not None:
            obs = obs_transform(obs)
        action, _ = model.predict(obs, action_masks=mask, deterministic=True)
        return int(action)

    return _policy


class TorchPolicy:
    """A ``train_torch.py`` model as a ``(env, obs, mask) -> action`` policy.

    Greedy by default — ``argmax`` over the masked logits, i.e. the mode of the
    distribution the agent acted under during training. ``sample=True`` draws
    from that distribution instead, from a generator seeded by ``seed`` so a
    stochastic evaluation is still reproducible.
    """

    def __init__(self, model: Any, *, device: str = "cpu",
                 sample: bool = False, seed: int = 0) -> None:
        import torch

        self.model = model
        self.device = device
        self.sample = sample
        self._generator = torch.Generator(device=device).manual_seed(seed) if sample else None

    def __call__(self, env: Any, obs: dict, mask: np.ndarray) -> int:
        import torch

        from .tensor_obs import TensorObs

        # ``obs`` is the env's own {"f": ndarray, "i": ndarray} (OBS_SCHEMA.md
        # §2); TensorObs.from_dict + a leading batch axis (obs[None]) is the
        # single-step-inference mirror of train_torch.py's rollout loop.
        obs_t = TensorObs.from_dict(obs, device=self.device)[None]
        mask_t = torch.as_tensor(np.asarray(mask), dtype=torch.bool, device=self.device).unsqueeze(0)
        with torch.no_grad():
            logits = self.model.action_logits(obs_t, mask_t)
            if not self.sample:
                return int(logits.argmax(dim=-1).item())
            probs = torch.softmax(logits, dim=-1)
            return int(torch.multinomial(probs[0], 1, generator=self._generator).item())


def torch_policy(model: Any, *, device: str = "cpu",
                 sample: bool = False, seed: int = 0) -> TorchPolicy:
    """Wrap an already-built model (see ``load_torch_policy`` to load one)."""
    return TorchPolicy(model, device=device, sample=sample, seed=seed)


def load_torch_policy(
    path: str,
    *,
    env_kind: str,
    env: Any,
    card_obs: str = "hybrid",
    device: str = "cpu",
    sample: bool = False,
    seed: int = 0,
) -> tuple[TorchPolicy, dict]:
    """Load a raw-torch checkpoint as a policy for ``env``.

    The architecture comes from the checkpoint's own ``arch`` stamp; the env's
    shape and schema are checked against it (``checkpoints.check_checkpoint``),
    so a mismatched env/schema/hidden refuses with the trainer's messages
    rather than a cryptic ``load_state_dict`` error. Returns
    ``(policy, checkpoint)``; the checkpoint is never written back.
    """
    from .checkpoints import load_agent

    obs_dim = (env.observation_space["f"].shape[0], env.observation_space["i"].shape[0])
    model, ckpt = load_agent(
        path,
        env_kind=env_kind,
        obs_dim=obs_dim,
        n_actions=env.action_space.n,
        card_obs=card_obs,
        device=device,
    )
    return TorchPolicy(model, device=device, sample=sample, seed=seed), ckpt


def ablation_transform(card_obs: str = "hybrid") -> Callable[[dict], dict]:
    """Zero the absolute-number/preview features of a raw observation — the
    same impoverishment ``AblatedObsEnv`` applies inside the env.

    ``numeric_obs_indices`` indexes ``obs["f"]`` only (OBS_SCHEMA.md §2: ids
    in ``obs["i"]`` are categorical, never numeric-ablated) — this used to
    index a flat obs array directly; the dict has to be copied one level
    deeper than ``dict.copy()`` alone, or zeroing ``obs["f"]`` in place would
    also mutate the caller's original array (the same reference)."""
    idx = numeric_obs_indices(card_obs)

    def _transform(obs: dict) -> dict:
        f = obs["f"].copy()
        f[idx] = 0.0
        return {"f": f, "i": obs["i"]}

    return _transform


# ── Win rate ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WinRateReport:
    episodes: int
    wins: int
    mean_turns: float
    mean_hp_left: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.episodes if self.episodes else 0.0


def evaluate_win_rate(
    policy: Policy,
    *,
    episodes: int = 100,
    seed: int = 0,
    env: Any | None = None,
) -> WinRateReport:
    """Roll the policy over ``episodes`` seeded episodes (seed, seed+1, …).

    ``env`` defaults to a fresh ``STS2FullCombatEnv()`` (the Act 1 pool); pass
    an ``AblatedObsEnv``-wrapped env to evaluate an ablation-trained model on
    the observations it was trained on."""
    if env is None:
        env = STS2FullCombatEnv()
    wins = 0
    turns: list[int] = []
    hp_left: list[int] = []
    for ep in range(episodes):
        obs, info = env.reset(seed=seed + ep)
        terminated = truncated = False
        while not (terminated or truncated):
            mask = env.action_masks()
            action = int(policy(env, obs, mask))
            if not mask[action]:
                # Illegal pick → first legal action, so the eval can't stall
                # (end turn on the combat env; phase-dependent on the run env).
                action = int(np.flatnonzero(mask)[0])
            obs, _reward, terminated, truncated, info = env.step(action)
        wins += int(info.get("is_success", False))
        # The combat env reports turns; the run env reports floors reached.
        turns.append(int(info.get("turn", info.get("floor", 0))))
        if "hp_left" in info:
            hp_left.append(int(info["hp_left"]))
        else:  # combat-env fallback (kept for wrapped envs without hp_left)
            hp_left.append(max(0, env.unwrapped._state.player.hp))
    return WinRateReport(episodes, wins, float(np.mean(turns)), float(np.mean(hp_left)))


# ── Run-scale evaluation ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunEvalReport:
    """Per-episode outcomes of a run-scale evaluation, plus the aggregates.

    Floors reached is the headline number: on the run envs a win rate near
    zero is normal for a long time, so *how far* the policy gets is what
    distinguishes two checkpoints. Everything is stored per episode so the
    report is comparable and reproducible, not just printable.
    """

    episodes: int
    floors: tuple[int, ...]          # max floor reached, per episode
    acts: tuple[int, ...]            # max act index reached (0-based), per episode
    victories: tuple[bool, ...]
    truncations: tuple[bool, ...]    # hit the step limit: neither win nor death
    hp_left: tuple[int, ...]         # end-of-run HP (0 when the run ended in death)
    decisions: tuple[int, ...]       # decisions answered, per episode

    @property
    def wins(self) -> int:
        return sum(self.victories)

    @property
    def truncated(self) -> int:
        return sum(self.truncations)

    @property
    def win_rate(self) -> float:
        return self.wins / self.episodes if self.episodes else 0.0

    @property
    def mean_floor(self) -> float:
        return float(np.mean(self.floors)) if self.floors else 0.0

    @property
    def median_floor(self) -> float:
        return float(np.median(self.floors)) if self.floors else 0.0

    @property
    def mean_decisions(self) -> float:
        return float(np.mean(self.decisions)) if self.decisions else 0.0

    @property
    def act_histogram(self) -> dict[int, int]:
        """act index (0-based) -> episodes that reached it."""
        hist: dict[int, int] = {}
        for act in self.acts:
            hist[act] = hist.get(act, 0) + 1
        return dict(sorted(hist.items()))

    @property
    def death_floors(self) -> tuple[int, ...]:
        """Floors the *lost* runs died on (truncated runs aren't deaths)."""
        return tuple(f for f, won, tr in
                     zip(self.floors, self.victories, self.truncations)
                     if not won and not tr)

    @property
    def death_acts(self) -> tuple[int, ...]:
        return tuple(a for a, won, tr in
                     zip(self.acts, self.victories, self.truncations)
                     if not won and not tr)

    @property
    def win_hp(self) -> tuple[int, ...]:
        return tuple(hp for hp, won in zip(self.hp_left, self.victories) if won)


def evaluate_run(
    policy: Policy,
    *,
    episodes: int = 20,
    seed: int = 0,
    env: Any | None = None,
) -> RunEvalReport:
    """Roll ``policy`` over ``episodes`` seeded full runs (seed, seed+1, …).

    ``env`` defaults to a fresh ``STS2RunEnv``; pass an
    ``STS2CurriculumRunEnv`` to evaluate the phase-1 curriculum. Given the same
    seed and env settings this is deterministic: same episodes, same report.
    """
    if env is None:
        from .run_env import STS2RunEnv

        env = STS2RunEnv()

    floors: list[int] = []
    acts: list[int] = []
    victories: list[bool] = []
    hp_left: list[int] = []
    decisions: list[int] = []
    trunc_flags: list[bool] = []

    for ep in range(episodes):
        obs, info = env.reset(seed=seed + ep)
        max_floor = int(info.get("floor", 0))
        max_act = int(info.get("act", 0))
        steps = 0
        terminated = truncated = False
        while not (terminated or truncated):
            mask = env.action_masks()
            action = int(policy(env, obs, mask))
            if not mask[action]:
                # Illegal pick → first legal action, so the eval can't stall.
                action = int(np.flatnonzero(mask)[0])
            obs, _reward, terminated, truncated, info = env.step(action)
            steps += 1
            max_floor = max(max_floor, int(info.get("floor", 0)))
            max_act = max(max_act, int(info.get("act", 0)))

        floors.append(max_floor)
        acts.append(max_act)
        victories.append(bool(info.get("is_success", False)))
        hp_left.append(int(info.get("hp_left", 0)))
        decisions.append(int(info.get("decisions", steps)))
        trunc_flags.append(bool(truncated and not terminated))

    return RunEvalReport(
        episodes=episodes,
        floors=tuple(floors),
        acts=tuple(acts),
        victories=tuple(victories),
        truncations=tuple(trunc_flags),
        hp_left=tuple(hp_left),
        decisions=tuple(decisions),
    )


# ── Probe accuracy ────────────────────────────────────────────────────────────


def evaluate_probes(
    policy: Policy, probes: Sequence[Probe] | None = None
) -> tuple[float, list[ProbeResult]]:
    """Run the lethal-arithmetic suite; returns (accuracy, per-probe results)."""
    results = run_probes(policy, probes)
    return probe_accuracy(results), results


def probe_summary(results: Sequence[ProbeResult]) -> str:
    """"6/8 (failed: lethal_edge_hold, weak_removes_kill)" — for report rows."""
    passed = sum(r.passed for r in results)
    failed = [r.probe_id for r in results if not r.passed]
    tail = f" (failed: {', '.join(failed)})" if failed else ""
    return f"{passed}/{len(results)}{tail}"
