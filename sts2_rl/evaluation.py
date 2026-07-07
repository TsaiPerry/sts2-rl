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


def ablation_transform(card_obs: str = "hybrid") -> Callable[[np.ndarray], np.ndarray]:
    """Zero the absolute-number/preview features of a raw observation — the
    same impoverishment ``AblatedObsEnv`` applies inside the env."""
    idx = numeric_obs_indices(card_obs)

    def _transform(obs: np.ndarray) -> np.ndarray:
        obs = obs.copy()
        obs[idx] = 0.0
        return obs

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
                action = 0   # illegal pick → end turn, so the eval can't stall
            obs, _reward, terminated, truncated, info = env.step(action)
        wins += int(info.get("is_success", False))
        turns.append(int(info.get("turn", 0)))
        hp_left.append(max(0, env.unwrapped._state.player.hp))
    return WinRateReport(episodes, wins, float(np.mean(turns)), float(np.mean(hp_left)))


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
