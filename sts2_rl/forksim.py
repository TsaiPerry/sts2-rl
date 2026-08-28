"""forksim.py — deterministic fork-by-replay over a run-env combat (Phase 3).

The RL run env is a greenlet-driven simulator with no state-copy operation:
a `RunState` is a live object graph (cards holding combat back-references,
relics wired into hook dispatch, a greenlet mid-flight), so `deepcopy` is
neither safe nor faithful. `CombatFork` gets branching anyway by REPLAY:
every fork re-creates a fresh `STS2RunEnv`, resets it onto the same forced
snapshot with the same seed, and re-issues the same prefix of actions. Two
replays of the same prefix are byte-identical observations because

  * `reset(seed=seed, ...)` rebuilds `env._rng = random.Random(seed)` — and
    `_make_run_state` hands THAT object to the `RunState`, so the run's whole
    stochastic stream (map roll, shuffles, monster moves, rewards) is a pure
    function of `seed` plus the actions taken;
  * the forced-snapshot reset path (`options={"drill_snapshot": snap}`,
    run_env.py's drill roll block) REPLACES the drill roll rather than
    running alongside it, so it draws no rng of its own and does not shift
    that stream;
  * the snapshot itself is data (deck/relics/hp/belt/gold/floor/encounter),
    rebuilt into fresh engine objects by `snapshots.build_start_state` inside
    `STS2RunEnv._drill_start_setup` — the same restore contract v20 drills
    already use in training.

`branch` is the one place a fork deliberately DIVERGES: after replaying the
prefix it re-seeds the run's rng from a salt (`0x5EED0000 + salt`) and then
steps the branch action, so the same salt reproduces one specific stochastic
future exactly while different salts sample different ones. This is the
substrate Tasks 8-9 (probe suite, expectimax search) stand on.

Known limits (inherited from the drill restore contract, not new here):
`_drill_start_setup` re-rolls the act map, so map LAYOUT is not the source
run's; a flag-only relic state (e.g. a spent Lizard Tail) does not survive a
snapshot (`snapshots.py` deviation #3); and an event-launched encounter has
no act module, so `_drill_start_setup` cannot restore it — `CombatFork`
rejects such a snapshot up front rather than tripping its assert.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .run_env import STS2RunEnv
from .snapshots import Snapshot, act_module_for_encounter

#: Salt base for `branch` — an arbitrary high constant so a salt of 0..N
#: lands far from any seed a caller is likely to also be using as `seed`.
BRANCH_SEED_BASE = 0x5EED0000


class CombatFork:
    """Fork-by-replay around one harvested combat start state.

    `snapshot` is a `snapshots.Snapshot` (schema 2); `seed` is the reset seed
    every replay uses; `env_kwargs` is passed straight to `STS2RunEnv`
    (`{"ascension": 10}` etc.) — the caller owns reward-shaping and env
    configuration, this class only owns determinism.
    """

    def __init__(self, snapshot: Snapshot, seed: int,
                 env_kwargs: "dict | None" = None) -> None:
        if act_module_for_encounter(snapshot.encounter_id) is None:
            raise ValueError(
                f"CombatFork: snapshot encounter {snapshot.encounter_id!r} is "
                f"event-launched (no act module) — not drillable, so it cannot "
                f"be replayed")
        self.snapshot = snapshot
        self.seed = int(seed)
        self.env_kwargs = dict(env_kwargs or {})

    # ── replay ────────────────────────────────────────────────────────────

    def _fresh_env(self) -> STS2RunEnv:
        """A brand-new env reset onto the forced snapshot. New env per call,
        never a recycled one: an env that has already been stepped carries
        greenlet + episode-tally state that only `reset` clears, and reusing
        one across forks is exactly the aliasing this module exists to
        avoid."""
        env = STS2RunEnv(**self.env_kwargs)
        env.reset(seed=self.seed,
                  options={"drill_snapshot": self.snapshot})
        return env

    def replay(self, actions: "list[int]") -> STS2RunEnv:
        """Fresh env at the snapshot, then `step` each action in order.

        Stops early if the episode ends (terminated/truncated) mid-prefix —
        stepping a finished env is a no-op against a `None` request, so the
        remaining actions would silently do nothing; returning the terminal
        env is the honest result. Identical calls give byte-identical
        `_build_obs()`.
        """
        env = self._fresh_env()
        for action in actions:
            _obs, _r, terminated, truncated, _info = env.step(int(action))
            if terminated or truncated:
                break
        return env

    def branch(self, actions: "list[int]", action: int,
               salt: int) -> "tuple[STS2RunEnv, float, bool]":
        """Replay `actions`, re-seed the run's rng from `salt`, then take
        `action`. Returns `(env, reward, done)`.

        `env._rng` IS the object the `RunState` draws from
        (`_make_run_state(rng=self._rng)`), so re-seeding it in place
        redirects every subsequent draw — shuffles, monster move rolls,
        reward rolls — onto the salt's stream. Same salt ⇒ same stochastic
        outcome; different salt ⇒ an independent sample of the same decision.
        """
        env = self.replay(actions)
        env._rng.seed(BRANCH_SEED_BASE + int(salt))
        _obs, reward, terminated, truncated, _info = env.step(int(action))
        return env, float(reward), bool(terminated or truncated)

    # ── rollout ───────────────────────────────────────────────────────────

    @staticmethod
    def in_combat(env: STS2RunEnv) -> bool:
        """True while the env's pending decision belongs to a live combat.

        The env exposes "where am I" as the pending `DecisionRequest`
        (`env._request`); `None` means the episode itself ended. The right
        predicate is that request's own `in_combat` flag, NOT
        `kind == COMBAT`: a fight also raises SELECT_CARDS / choice requests
        while it is live (card selectors from Gnarled Hammer, Kifuda,
        Whispering Earring, select-hand-cards cards, potions), and those
        carry a non-COMBAT `kind`. `RunDriver._ask` stamps
        `request.in_combat = request.combat is not None or self._combat is
        not None` on EVERY request (driver.py:390) and clears `_combat`
        before the post-combat reward screens (driver.py:594), so the flag is
        True for combat decisions and mid-combat selectors alike and False at
        MAP/REWARD/EVENT. Keying on `kind` instead would stop a rollout
        mid-fight and bootstrap as if the combat had resolved — and stop
        sibling branches at different depths, which is exactly the
        apples-to-oranges comparison the search in Tasks 8-9 must not make.
        """
        request = getattr(env, "_request", None)
        return request is not None and bool(request.in_combat)

    def rollout(self, env: STS2RunEnv, policy: Any, max_steps: int = 120,
                gamma: float = 0.999) -> float:
        """Continue `env` under `policy` to the end of the combat and return

            Σ_k γ^k r_k   +   γ^K V(s_K)

        where the sum runs over the steps actually taken (k from 0) and the
        leaf bootstrap is the critic's value of the state the rollout stops
        in — 0 when the episode TERMINATED (a terminal state has no future
        by definition; truncation and the combat-exit stop are NOT terminal
        and do bootstrap).

        The rollout stops when the combat's request goes away (the next
        decision is a map/reward/event screen — the fight is resolved), when
        the episode ends, or after `max_steps` steps. `policy` is an
        `evaluation.TorchPolicy`-shaped callable `(env, obs, mask) -> action`
        carrying the model on `.model`; `policy.model.get_value` supplies V.
        """
        total = 0.0
        discount = 1.0
        terminated = False
        steps = 0
        while steps < max_steps and self.in_combat(env):
            obs = env._build_obs()
            mask = env.action_masks()
            action = int(policy(env, obs, mask))
            _obs, reward, terminated, truncated, _info = env.step(action)
            total += discount * float(reward)
            discount *= gamma
            steps += 1
            if terminated or truncated:
                break
        if terminated:
            return total
        return total + discount * self._leaf_value(env, policy)

    @staticmethod
    def _leaf_value(env: STS2RunEnv, policy: Any) -> float:
        """V(s) for the env's CURRENT observation, via the policy's model."""
        import torch

        from .tensor_obs import TensorObs

        model = getattr(policy, "model", None)
        if model is None:
            raise AttributeError(
                "CombatFork.rollout: policy has no `.model` — the leaf "
                "bootstrap needs `policy.model.get_value`")
        device = getattr(policy, "device", "cpu")
        obs_t = TensorObs.from_dict(env._build_obs(), device=device)[None]
        with torch.no_grad():
            return float(model.get_value(obs_t).reshape(-1)[0].item())


# ─────────────────────────────────────────────────────────────────────────
# Prior helpers — the policy's own action distribution, split out of
# `TorchPolicy.__call__` so a searcher can read the distribution AND draw
# from it through the identical code path (softmax over masked logits,
# `torch.multinomial` with an explicit generator). Sharing the path is what
# lets `eval_search.py`'s policy arm and search arm be compared decision for
# decision: a "flip" then means the search disagreed with the policy, never
# that the two arms sampled through subtly different plumbing.
# ─────────────────────────────────────────────────────────────────────────


def prior(policy: Any, env: STS2RunEnv) -> "tuple[np.ndarray, np.ndarray]":
    """`(probs, mask)` for the env's CURRENT decision under `policy`.

    `probs` is float32 and already zero on illegal actions —
    `model.action_logits` masked-fills them before the softmax — so
    `argmax(probs)` is the greedy (prior-argmax) action and `probs` needs no
    further masking. `mask` is the env's boolean legality vector, returned
    alongside so callers can enumerate legal ids without a second
    `action_masks()` call (which would rebuild it).
    """
    import torch

    from .tensor_obs import TensorObs

    device = getattr(policy, "device", "cpu")
    mask = np.asarray(env.action_masks(), dtype=bool)
    obs_t = TensorObs.from_dict(env._build_obs(), device=device)[None]
    mask_t = torch.as_tensor(mask, dtype=torch.bool, device=device).unsqueeze(0)
    with torch.no_grad():
        logits = policy.model.action_logits(obs_t, mask_t)
        probs = torch.softmax(logits, dim=-1)[0]
    return probs.detach().cpu().numpy(), mask


def sample_from_prior(probs: np.ndarray, seed: int, device: str = "cpu") -> int:
    """Draw one action from `prior`'s distribution with a freshly seeded
    generator — the same `torch.multinomial(probs, 1, generator=...)` draw
    `TorchPolicy(sample=True)` makes, but reproducible from `seed` alone
    rather than from however far a shared generator happens to have advanced.
    Reseeding per decision is what keeps a measurement run reproducible even
    though search rollouts share the policy object and consume its
    generator."""
    import torch

    gen = torch.Generator(device=device).manual_seed(int(seed))
    p = torch.as_tensor(np.asarray(probs, dtype=np.float32), device=device)
    return int(torch.multinomial(p, 1, generator=gen).item())


def reseed_policy(policy: Any, seed: int) -> None:
    """Reset a sampling `TorchPolicy`'s generator to `seed`; a no-op for a
    greedy policy (no generator to reset).

    Reaches for `policy._generator` because `TorchPolicy` exposes no public
    reseed today, and adding one is out of this task's file scope. Guarded by
    `getattr` so any `(env, obs, mask) -> action` callable still works as a
    rollout policy.
    """
    gen = getattr(policy, "_generator", None)
    if gen is not None:
        gen.manual_seed(int(seed))


# ─────────────────────────────────────────────────────────────────────────
# Expectimax
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SearchResult:
    """One decision's search outcome.

    `action` is what the search chose, `prior_argmax` what the bare policy
    would have taken greedily; `searched` is False for a decision the search
    declined (fewer than two legal actions — nothing to compare), in which
    case `action == prior_argmax` and no rollouts were spent.
    """

    action: int
    prior_argmax: int
    searched: bool
    candidates: "tuple[int, ...]"
    scores: "tuple[float, ...]"
    n_rollouts: int

    @property
    def flipped(self) -> bool:
        """The measurement's headline event: the search moved off the policy's
        prior argmax. False by construction on an unsearched decision."""
        return self.searched and self.action != self.prior_argmax


def expectimax(fork: CombatFork, actions: "list[int]", policy: Any,
               k: int, m: int, *, env: "STS2RunEnv | None" = None,
               salt_base: int = 0, rollout_seed_base: "int | None" = None,
               max_steps: int = 120, gamma: float = 0.999,
               mass_cap: "float | None" = None) -> SearchResult:
    """One-ply expectimax over the policy's top-`k` legal actions, `m`
    stochastic branches each, scored by `CombatFork.rollout`. `mass_cap`
    (optional) further shrinks the candidate set to the smallest prior-mass
    prefix — see `top_k_actions`; `n_rollouts` in the result reflects the
    actual (possibly shrunk) candidate count, so a measurement's rollout
    tally prices the cap honestly.

    For each candidate `a`, each salt `j`:

        score(a, j) = r(a, j) + γ · [ 0 if terminal else rollout(after a) ]

    i.e. exactly `rollout`'s own n-step-return-plus-leaf-V quantity shifted
    one step earlier, so a candidate's score and a rollout's return are the
    same currency. The candidate with the best MEAN over the `m` salts wins;
    ties go to the higher-prior candidate (candidates are enumerated in
    descending prior order, and `>` keeps the incumbent), so a tie never
    manufactures a flip.

    **Common random numbers.** The salt set `salt_base .. salt_base+m-1` is
    the SAME for every candidate, and the rollout policy is reseeded to
    `rollout_seed_base + j` before branch `j` of every candidate. So salt `j`
    pins one stochastic future — the same shuffles, the same monster move
    rolls, the same policy action draws — and the candidates are compared
    across an identical set of `m` worlds. Without that, at m=8 the
    between-candidate difference would be swamped by which futures each
    candidate happened to draw. The CALLER owns collision-freedom of
    `salt_base` / `rollout_seed_base` across decisions and fights (see
    `tools/eval_search.py`'s `_salt_base` / `_rollout_seed_base`).

    `env`, when given, must be a live env already positioned at `actions` —
    it is used only to read the prior, saving one replay per decision. The
    branches always come from `fork.branch(actions, ...)`, i.e. from a fresh
    replay, so `env` is never mutated here.
    """
    if k < 1:
        raise ValueError(f"expectimax: k must be >= 1, got {k}")
    if m < 1:
        raise ValueError(f"expectimax: m must be >= 1, got {m}")
    if env is None:
        env = fork.replay(actions)
    if rollout_seed_base is None:
        rollout_seed_base = salt_base

    probs, mask = prior(policy, env)
    legal = np.flatnonzero(mask)
    if legal.size == 0:
        raise ValueError("expectimax: no legal action at this decision")
    prior_argmax = int(legal[int(np.argmax(probs[legal]))])
    if legal.size == 1:
        return SearchResult(action=prior_argmax, prior_argmax=prior_argmax,
                            searched=False, candidates=(prior_argmax,),
                            scores=(float("nan"),), n_rollouts=0)

    candidates = top_k_actions(probs, mask, k, mass_cap=mass_cap)
    salts = [salt_base + j for j in range(m)]

    best_action = prior_argmax
    best_score = -float("inf")
    means: list[float] = []
    for a in candidates:
        total = 0.0
        for j, salt in enumerate(salts):
            reseed_policy(policy, rollout_seed_base + j)
            branch_env, reward, done = fork.branch(actions, a, salt)
            if done:
                # `branch` collapses terminated/truncated into one flag; the
                # env's own `_result` tells them apart. A TERMINAL state has
                # no future to bootstrap (rollout's own rule); a truncation
                # is a harness artifact and still gets the leaf value.
                terminal = getattr(branch_env, "_result", None) is not None
                cont = 0.0 if terminal else CombatFork._leaf_value(branch_env, policy)
            else:
                cont = fork.rollout(branch_env, policy,
                                    max_steps=max_steps, gamma=gamma)
            total += reward + gamma * cont
        mean = total / len(salts)
        means.append(mean)
        if mean > best_score:
            best_score = mean
            best_action = int(a)

    return SearchResult(action=best_action, prior_argmax=prior_argmax,
                        searched=True, candidates=tuple(int(a) for a in candidates),
                        scores=tuple(means), n_rollouts=len(candidates) * len(salts))


def top_k_actions(probs: np.ndarray, mask: np.ndarray, k: int, *,
                  mass_cap: "float | None" = None,
                  min_k: int = 2) -> "list[int]":
    """The `k` highest-prior LEGAL actions, highest first, ties broken by
    ascending action id.

    Sorting `(-p, a)` rather than calling `argsort` on the probabilities
    alone makes the tie order explicit and platform-independent: two actions
    the policy is exactly indifferent between (common — duplicate cards in
    hand produce bit-identical logits) must always enter the candidate set in
    the same order, or the search's tie-break, and with it the flip rate,
    becomes a function of numpy's sort implementation.

    `mass_cap`, when set, shrinks the list further: keep the smallest prefix
    whose cumulative prior mass reaches the cap, clamped to `[min_k, k]`.
    Rationale: after 100M+ steps the prior is concentrated (train-time
    entropy ~0.5 nats ≈ 1.6 effective actions), so a fixed k=5 routinely
    spends most of its k·m rollouts scoring sub-1% candidates the softmax
    target will zero out anyway; the cap adapts breadth to how torn the
    policy actually is. `probs` must be the masked softmax (`prior`'s
    contract: legal mass sums to 1), so the cumulative sum is well-defined.
    `min_k` floors the list at 2 so a searched decision always compares
    something (`expectimax` handles the 1-legal-action case before calling
    here). `None` (the default) preserves the fixed-k behavior exactly.
    """
    legal = np.flatnonzero(np.asarray(mask, dtype=bool))
    ranked = sorted(legal.tolist(), key=lambda a: (-float(probs[a]), int(a)))
    ranked = ranked[: max(1, int(k))]
    if mass_cap is None:
        return ranked
    if not 0.0 < mass_cap <= 1.0:
        raise ValueError(f"top_k_actions: mass_cap must be in (0, 1], got {mass_cap}")
    cum = 0.0
    keep = len(ranked)
    for i, a in enumerate(ranked):
        cum += float(probs[a])
        if cum >= mass_cap:
            keep = i + 1
            break
    return ranked[: max(min(min_k, len(ranked)), keep)]


def masked_random_policy(rng: "random.Random | None" = None) -> Callable:
    """A `(env, obs, mask) -> action` uniform-over-legal policy, for probing
    a fork without a checkpoint. Not usable as a `rollout` policy (no
    `.model` for the leaf value) — `rollout` is for value-bearing policies;
    this is for driving `replay` prefixes in tests and tooling."""
    rng = rng or random.Random(0)

    def _policy(_env: Any, _obs: dict, mask: np.ndarray) -> int:
        legal = np.flatnonzero(np.asarray(mask, dtype=bool))
        if legal.size == 0:
            return 0
        return int(rng.choice(legal.tolist()))

    return _policy
