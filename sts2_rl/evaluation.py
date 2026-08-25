"""Policy evaluation — win rate and lethal-probe accuracy side by side.

OBS_PLAN Phase 4 (steps 11–12): probe accuracy is a first-class metric next to
win rate, and the same evaluators drive the full-vs-ablated observation
ablation. CLIs: ``py eval.py --env full`` and ``py test/ablation.py``.

A *policy* here is any callable ``(env, obs, mask) -> action int`` —
``masked_random_policy`` / ``model_policy`` are the adapters, and
``probes.lethal_oracle`` is the scripted reference player.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
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
                 sample: bool = False, seed: int = 0,
                 merge_duplicates: bool = False) -> None:
        import torch

        self.model = model
        self.device = device
        self.sample = sample
        self.merge_duplicates = merge_duplicates
        self._generator = torch.Generator(device=device).manual_seed(seed) if sample else None
        self._layout_cache: dict[tuple[int, int], Any] = {}

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
                if self.merge_duplicates:
                    layout = self._layout_for(obs)
                    keys = play_group_keys(obs, mask, layout)
                    action = merged_greedy_action(
                        logits[0].detach().cpu().numpy(), np.asarray(mask, dtype=bool), keys)
                    assert action >= 0, "merged_greedy_action found no legal action"
                    return action
                return int(logits.argmax(dim=-1).item())
            probs = torch.softmax(logits, dim=-1)
            return int(torch.multinomial(probs[0], 1, generator=self._generator).item())


    def _layout_for(self, obs: dict) -> Any:
        """The ObsLayout whose dims match ``obs`` — the combat env's or the
        run env's (which prefixes the combat block "combat."). Cached per
        (f_dim, i_dim)."""
        key = (int(np.asarray(obs["f"]).shape[-1]), int(np.asarray(obs["i"]).shape[-1]))
        layout = self._layout_cache.get(key)
        if layout is None:
            from . import full_env, run_env

            for candidate in (full_env.combat_obs_layout(), run_env.run_obs_layout()):
                if (candidate.f_dim, candidate.i_dim) == key:
                    layout = candidate
                    break
            if layout is None:
                raise ValueError(
                    f"merge_duplicates: no known obs layout has dims {key} "
                    f"(combat {full_env.combat_obs_layout().f_dim}/"
                    f"{full_env.combat_obs_layout().i_dim}, run "
                    f"{run_env.run_obs_layout().f_dim}/{run_env.run_obs_layout().i_dim})")
            self._layout_cache[key] = layout
        return layout


def hand_slices(layout: Any) -> tuple[slice, slice]:
    """``(hand.ids, hand.f)`` slices of ``layout`` — the combat env names
    them bare, the run env under the ``combat.`` prefix."""
    if "hand.ids" in layout.i_slices:
        return layout.i_slices["hand.ids"], layout.f_slices["hand.f"]
    return layout.i_slices["combat.hand.ids"], layout.f_slices["combat.hand.f"]


def play_group_keys(obs: dict, mask: np.ndarray, layout: Any) -> list[str | None]:
    """One group key per action id, or None.

    Legal ``play`` actions whose hand instance the model cannot tell apart
    share a key: the ``hand.ids`` triple (card id, affliction id, enchantment
    id), the ``hand.f`` upgrade-level cell (``full_env.CARD_UPGRADE_FEATURE``)
    and the target slot. Upgrades / enchantments / afflictions therefore NEVER
    merge with their plain counterparts (Perry, 2026-08-22). Everything else
    — end turn, potions, out-of-combat actions, masked-out ids — is None
    (its own singleton group). Mirrors SpireBot's OnnxPolicyCore.PlayGroupKeys.
    """
    from . import full_env

    i_vec = np.asarray(obs["i"]).reshape(-1)
    f_vec = np.asarray(obs["f"]).reshape(-1)
    ids_sl, f_sl = hand_slices(layout)
    mask = np.asarray(mask, dtype=bool).reshape(-1)
    keys: list[str | None] = [None] * len(mask)
    base = full_env.COMBAT_PLAY_BASE
    for h in range(full_env.MAX_HAND):
        card_id = int(i_vec[ids_sl.start + h * 3])
        affl_id = int(i_vec[ids_sl.start + h * 3 + 1])
        ench_id = int(i_vec[ids_sl.start + h * 3 + 2])
        upgrade = float(f_vec[f_sl.start + h * full_env.N_CARD_FEATURES + full_env.CARD_UPGRADE_FEATURE])
        for e in range(full_env.MAX_ENEMIES):
            a = base + h * full_env.MAX_ENEMIES + e
            if a >= len(mask) or not mask[a]:
                continue
            keys[a] = f"play:{card_id}:{affl_id}:{ench_id}:{upgrade:.4f}:{e}"
    return keys


def merged_greedy_action(logits: np.ndarray, mask: np.ndarray,
                         keys: list[str | None]) -> int:
    """Argmax over GROUPS of legal actions: softmax the legal logits, sum the
    probability of every action sharing a key (None = singleton), take the
    heaviest group, and dispatch its highest-logit member. Returns -1 when no
    action is legal. With all-None keys this is plain argmax."""
    logits = np.asarray(logits, dtype=np.float64).reshape(-1)
    mask = np.asarray(mask, dtype=bool).reshape(-1)
    legal = np.flatnonzero(mask)
    if legal.size == 0:
        return -1
    z = logits[legal]
    p = np.exp(z - z.max())
    p /= p.sum()
    group_mass: dict[Any, float] = {}
    group_best: dict[Any, tuple[float, int]] = {}
    for prob, a in zip(p, legal):
        k = keys[a] if a < len(keys) and keys[a] is not None else ("__single__", int(a))
        group_mass[k] = group_mass.get(k, 0.0) + float(prob)
        cand = (float(logits[a]), -int(a))
        if k not in group_best or cand > group_best[k]:
            group_best[k] = cand
    best_key = max(group_mass, key=group_mass.get)
    return -group_best[best_key][1]


def torch_policy(model: Any, *, device: str = "cpu",
                 sample: bool = False, seed: int = 0,
                 merge_duplicates: bool = False) -> TorchPolicy:
    """Wrap an already-built model (see ``load_torch_policy`` to load one)."""
    return TorchPolicy(model, device=device, sample=sample, seed=seed,
                       merge_duplicates=merge_duplicates)


def load_torch_policy(
    path: str,
    *,
    env_kind: str,
    env: Any,
    card_obs: str = "hybrid",
    device: str = "cpu",
    sample: bool = False,
    seed: int = 0,
    merge_duplicates: bool = False,
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
    return TorchPolicy(model, device=device, sample=sample, seed=seed,
                       merge_duplicates=merge_duplicates), ckpt


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

    # Per-episode return and the behavior tallies the run envs report in
    # `info` at episode end (run_env._count_behavior). Default to () so a
    # report built from an env that emits none of them stays constructible.
    seeds: tuple[int, ...] = ()      # the seed each episode ran on
    returns: tuple[float, ...] = ()  # summed step reward, per episode
    end_turns: tuple[int, ...] = ()
    energy_unspent: tuple[float, ...] = ()
    card_offers: tuple[int, ...] = ()
    card_takes: tuple[int, ...] = ()
    rest_visits: tuple[int, ...] = ()      # rest sites visited (any answer)
    rest_heals: tuple[int, ...] = ()       # of those, visits that healed
    rest_upgrades: tuple[int, ...] = ()    # of those, visits that upgraded
    # v15: the same rest split conditioned on entering the site at
    # hp/max_hp >= run_env.HIHP_REST_THRESHOLD (0.65) -- the rest-economy
    # gate metric ("does it upgrade when healthy?").
    rest_visits_hihp: tuple[int, ...] = ()
    rest_upgrades_hihp: tuple[int, ...] = ()
    # v7 (plan Task 8): behavior counters + per-card exposure tallies.
    upgrades: tuple[int, ...] = ()         # permanent card upgrades gained
    removes: tuple[int, ...] = ()          # cards removed from the deck
    elites_won: tuple[int, ...] = ()       # elite fights won
    # v11.1: elite rooms ENTERED (win or lose) — `elites_won` misses every
    # death at an elite (the win tally fires on the rewards screen).
    elites_fought: tuple[int, ...] = ()
    potions_obtained: tuple[int, ...] = ()
    potions_used: tuple[int, ...] = ()
    # v8 (plan Task 2): potion ledger USE classification + timing.
    potions_used_elite: tuple[int, ...] = ()
    potions_used_boss: tuple[int, ...] = ()
    potions_used_normal: tuple[int, ...] = ()
    potions_expired: tuple[int, ...] = ()          # held belt count at episode end
    potion_use_hp: tuple[float, ...] = ()          # sum of hp/max_hp at each drink
    # v21 (potion option-value spec): per-episode sums/counts.
    potion_v_at_use: tuple[float, ...] = ()
    potions_wasted: tuple[int, ...] = ()
    potions_bought: tuple[int, ...] = ()
    potion_rewards_skipped: tuple[int, ...] = ()
    potion_rewards_forced: tuple[int, ...] = ()
    potion_relic_picks: tuple[int, ...] = ()
    # v22: voluntary discards + the skip-context records ({offered, belt,
    # floor} per open-slot reward skip — selectivity-vs-aversion read).
    potions_discarded: tuple[int, ...] = ()
    potion_skips: tuple[dict, ...] = ()
    # v23: per-episode card-reward offer/take counts split by 0-based act
    # ({act: count} dicts) — the per-act take-rate baseline (report-only,
    # no guardrail; a whole-run rate hides act-conditional drift).
    card_offers_by_act: tuple[dict, ...] = ()
    card_takes_by_act: tuple[dict, ...] = ()
    # v8 (plan Task 3): relics gained tally (starting relic never counts).
    relics: tuple[int, ...] = ()
    # v8 (plan Task 1, plan Task 5 threading): HP lost per episode -- a
    # sloppiness gauge, tracked independent of --hp-potential-scale shaping.
    hp_lost: tuple[int, ...] = ()
    # v20 (Task 3b): HP lost inside BOSS combats only -- the
    # --boss-hp-loss-penalty term's read instrument.
    boss_hp_lost: tuple[int, ...] = ()
    # v8 s7 gate ("mean hp overall" < "mean hp-at-use"): the env keeps no
    # running mean-hp counter of its own, so `evaluate_run` samples the
    # `run.hp_ratio` observation feature (OBS_SCHEMA.md -- the same number
    # already shown to the policy every decision, via the env's own
    # `_layout`) at each decision point. Per-episode sum + count rather than
    # a running mean so pooling across episodes is exact (see
    # `mean_hp_overall`'s docstring for why pooled, not mean-of-means).
    hp_ratio_sum: tuple[float, ...] = ()
    hp_ratio_steps: tuple[int, ...] = ()
    # Merged over all episodes: card class name -> count. `field` defaults
    # because dicts are mutable (still treated as immutable once built).
    card_offer_counts: dict[str, int] = field(default_factory=dict)
    # 2026-08-23 hold-duration metric: every potion-instance record pooled
    # over episodes ({id, held, outcome, room, v, pickup_floor, floor}).
    potion_holds: tuple[dict, ...] = ()
    card_take_counts_raw: dict[str, int] = field(default_factory=dict)
    # Merged over all episodes: rarity value -> {card class name -> copies}
    # in the deck each run ENDED with (sts2_rl.deck_stats). Starter,
    # colorless, curse and quest cards are already filtered out upstream.
    deck_rarity_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    # Merged over all episodes: (event id, page, option key) -> times chosen
    # (run_env `ep_event_choices`); rendered by `write_events_csv`.
    event_choice_counts_raw: dict[tuple[str, str, str], int] = field(default_factory=dict)

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

    @property
    def mean_return(self) -> float:
        return float(np.mean(self.returns)) if self.returns else 0.0

    @property
    def energy_unspent_per_turn(self) -> float:
        """Mean energy left unspent at each real end-turn.

        Pooled over episodes (total energy / total end-turns), NOT a mean of
        per-episode means: episodes differ enormously in turn count, and
        train_torch's `energy_unspent` column pools the same way — the two
        numbers have to be comparable. 0.0 rather than NaN when the policy
        never ended a turn, so no report row prints `nan`."""
        turns = sum(self.end_turns)
        return sum(self.energy_unspent) / turns if turns else 0.0

    @property
    def card_take_rate(self) -> float:
        """Fraction of resolved card-reward screens the policy took a card on
        (pooled like `energy_unspent_per_turn`; 0.0 when none were offered)."""
        offers = sum(self.card_offers)
        return sum(self.card_takes) / offers if offers else 0.0

    @property
    def card_take_rate_by_act(self) -> dict[int, tuple[int, int, float]]:
        """0-based act -> (offers, takes, take rate), pooled over episodes
        like `card_take_rate` (v23 report-only baseline)."""
        offers: dict[int, int] = {}
        takes: dict[int, int] = {}
        for ep in self.card_offers_by_act:
            for act, n in ep.items():
                offers[act] = offers.get(act, 0) + int(n)
        for ep in self.card_takes_by_act:
            for act, n in ep.items():
                takes[act] = takes.get(act, 0) + int(n)
        return {act: (n, takes.get(act, 0), takes.get(act, 0) / n if n else 0.0)
                for act, n in sorted(offers.items())}

    @property
    def rest_heal_rate(self) -> float:
        """Share of rest-site visits the policy healed at.

        Denominator is every visit, so a site the policy simply left counts
        against both this and `rest_upgrade_rate`. The two can sum above 1.0:
        one visit can do both (Miniature Tent)."""
        visits = sum(self.rest_visits)
        return sum(self.rest_heals) / visits if visits else 0.0

    @property
    def rest_upgrade_rate(self) -> float:
        """Share of rest-site visits the policy upgraded a card at.

        Note this does NOT exclude visits where upgrading was impossible (a
        fully-upgraded deck makes REST_SMITH illegal), so a low rate late in a
        run can mean "nothing left to upgrade" rather than "chose not to"."""
        visits = sum(self.rest_visits)
        return sum(self.rest_upgrades) / visits if visits else 0.0

    @property
    def potion_use_rate(self) -> float:
        """Potions drunk per potion obtained, pooled over episodes like the
        other rates; 0.0 when none obtained.

        `potions_used` (v8 Task 2) counts only actual drinks now — a belt
        loss with no drink answer behind it (e.g. an event trading a potion
        away) moves the v8 ledger but not this count."""
        obtained = sum(self.potions_obtained)
        return sum(self.potions_used) / obtained if obtained else 0.0

    @property
    def potion_use_hp_mean(self) -> float:
        """Mean hp/max_hp AT THE MOMENT a potion was drunk, pooled over
        episodes like the other rates — "drinks happen in trouble, not on
        pickup" gauge (v8 plan Task 2). 0.0 when nothing was drunk."""
        used = sum(self.potions_used)
        return sum(self.potion_use_hp) / used if used else 0.0

    @property
    def potion_elite_share(self) -> float:
        """(elite + boss uses) / all uses, pooled over episodes like the
        other rates (v8 plan Task 5) -- informational, no target. 0.0 when
        nothing was drunk."""
        used = sum(self.potions_used)
        return ((sum(self.potions_used_elite) + sum(self.potions_used_boss))
                / used if used else 0.0)

    @property
    def mean_hp_lost(self) -> float:
        """Mean HP lost per episode (v8 plan Task 1/5) -- a sloppiness
        gauge, tracked whether or not --hp-potential-scale shaping is on."""
        return float(np.mean(self.hp_lost)) if self.hp_lost else 0.0

    @property
    def mean_potions_used(self) -> float:
        """Mean potions drunk per episode (a raw count, distinct from
        `potion_use_rate`'s obtained-normalized share)."""
        return float(np.mean(self.potions_used)) if self.potions_used else 0.0

    @property
    def mean_potions_expired(self) -> float:
        """Mean belt count still held at episode end -- a hoarding gauge
        (v8 plan Task 2/5)."""
        return (float(np.mean(self.potions_expired))
                if self.potions_expired else 0.0)

    @property
    def mean_relics(self) -> float:
        """Mean relics gained per episode (v8 plan Task 3/5)."""
        return float(np.mean(self.relics)) if self.relics else 0.0

    @property
    def mean_elites(self) -> float:
        """Mean elites per episode (v8 s7 gate's "elites/episode").

        This is elite WINS (`ep_elites_won`) under the gate's name -- a lost
        elite fight isn't counted here; the per-episode `elites_fought`
        column (v11.1) carries attempts, win or lose."""
        return float(np.mean(self.elites_won)) if self.elites_won else 0.0

    @property
    def hp_lost_per_floor(self) -> float:
        """`mean_hp_lost` / `mean_floor` (v8 s7 gate's "hp_lost/floor").

        A ratio of the two aggregate means, NOT a per-episode mean of
        per-episode ratios: early deaths can reach floor 0-1, where a
        per-episode hp_lost/floor blows up or needs an arbitrary floor-0
        guard; dividing the pooled means sidesteps that and matches how
        every other pooled rate on this class is built. 0.0 when
        `mean_floor` is 0 (no episodes, or a report built with none run)."""
        floor = self.mean_floor
        return self.mean_hp_lost / floor if floor else 0.0

    @property
    def mean_potions_expired_deaths(self) -> float:
        """Mean belt count held at episode end, over DEATH episodes only
        (v8 s7 gate: `potions_expired` <= 1.5 ON DEATHS specifically --
        dying with a full belt means the timing bar beat survival; the same
        thing on a WIN is fine play and excluded here). 0.0 when there were
        no deaths (or no `potions_expired` tuple at all)."""
        if not self.potions_expired:
            return 0.0
        deaths = [p for p, won, tr in
                  zip(self.potions_expired, self.victories, self.truncations)
                  if not won and not tr]
        return float(np.mean(deaths)) if deaths else 0.0

    @property
    def mean_potion_v_at_use(self) -> float:
        """Mean option value v(s) spent per drink, pooled (v21). 0 when
        nothing was drunk."""
        used = sum(self.potions_used)
        return sum(self.potion_v_at_use) / used if used else 0.0

    @property
    def potions_wasted_rate(self) -> float:
        """(near-)nil drinks / all drinks, pooled (v21 metric rule)."""
        used = sum(self.potions_used)
        return sum(self.potions_wasted) / used if used else 0.0

    @property
    def mean_potions_bought(self) -> float:
        return float(np.mean(self.potions_bought)) if self.potions_bought else 0.0

    @property
    def mean_potion_rewards_skipped(self) -> float:
        return float(np.mean(self.potion_rewards_skipped)) if self.potion_rewards_skipped else 0.0

    @property
    def mean_potion_rewards_forced(self) -> float:
        return float(np.mean(self.potion_rewards_forced)) if self.potion_rewards_forced else 0.0

    @property
    def mean_potion_relic_picks(self) -> float:
        return float(np.mean(self.potion_relic_picks)) if self.potion_relic_picks else 0.0

    @property
    def mean_potions_discarded(self) -> float:
        return float(np.mean(self.potions_discarded)) if self.potions_discarded else 0.0

    @property
    def potion_skip_belt_histogram(self) -> dict[int, int]:
        """Voluntary reward skips binned by belt occupancy at skip time.
        Skips at 0-1 held read as aversion; at 2-3 held as selectivity."""
        bins = {0: 0, 1: 0, 2: 0, 3: 0}
        for rec in self.potion_skips:
            bins[min(len(rec.get("belt", [])), 3)] += 1
        return bins

    @property
    def mean_hp_overall(self) -> float:
        """Mean `run.hp_ratio` (hp/max_hp) sampled at every decision point,
        pooled over episodes like `energy_unspent_per_turn` -- the v8 s7
        gate's "mean hp overall" side of "mean hp-at-use < mean hp overall".

        PROXY, clearly labeled per plan Task 7: the env keeps no running
        mean-hp counter (`ep_*`) of its own, so this doesn't compare to
        `potion_use_hp_mean` via a new env counter -- it reads the SAME
        `run.hp_ratio` observation feature the policy already sees each
        decision (see `hp_ratio_sum`'s docstring), so both sides of the gate
        are the identical hp/max_hp ratio, just sampled at different
        moments (every decision vs. potion-drink decisions only). 0.0 if the
        report's env exposed no such feature (e.g. a hand-built report in a
        test, or a non-run env)."""
        steps = sum(self.hp_ratio_steps)
        return sum(self.hp_ratio_sum) / steps if steps else 0.0

    @property
    def potion_hold_table(self) -> dict[str, dict]:
        """Per potion id (most picked first): picked / used / held (at episode
        end) / lost counts, mean floors held over USED instances and over all,
        mean v(s) at use, and the elite+boss share of uses."""
        by_id: dict[str, list[dict]] = {}
        for rec in self.potion_holds:
            by_id.setdefault(rec["id"], []).append(rec)
        table: dict[str, dict] = {}
        for pid, recs in sorted(by_id.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            used = [r for r in recs if r["outcome"] == "used"]
            tier = sum(1 for r in used if r["room"] in ("elite", "boss"))
            vs = [r["v"] for r in used if r["v"] is not None]
            table[pid] = {
                "picked": len(recs),
                "used": len(used),
                "held": sum(1 for r in recs if r["outcome"] == "held"),
                "lost": sum(1 for r in recs if r["outcome"] == "lost"),
                "discarded": sum(1 for r in recs if r["outcome"] == "discarded"),
                "mean_hold_used": (sum(r["held"] for r in used) / len(used)) if used else 0.0,
                "mean_hold_all": sum(r["held"] for r in recs) / len(recs),
                "v_at_use": (sum(vs) / len(vs)) if vs else 0.0,
                "tier_share": (tier / len(used)) if used else 0.0,
            }
        return table

    @property
    def mean_potion_hold_used(self) -> float:
        """Mean floors held by potions that were actually drunk, pooled."""
        used = [r["held"] for r in self.potion_holds if r["outcome"] == "used"]
        return (sum(used) / len(used)) if used else 0.0

    @property
    def discard_repickup_2fl(self) -> tuple[int, int]:
        """(voluntary discards followed by ANY potion pickup within 2 floors
        of the same episode, total voluntary discards) — the v22 fork read
        that was uninstrumented then (pooled hold records carried no episode
        key). Counts only records `evaluate_run` tagged with an episode
        "seed" (v23), so a report built from untagged records reports (0, 0)
        rather than falsely linking pickups across episodes."""
        by_seed: dict[Any, list[dict]] = {}
        for rec in self.potion_holds:
            if "seed" in rec:
                by_seed.setdefault(rec["seed"], []).append(rec)
        hits = total = 0
        for recs in by_seed.values():
            for rec in recs:
                if rec["outcome"] != "discarded":
                    continue
                total += 1
                hits += any(rec["floor"] < r["pickup_floor"] <= rec["floor"] + 2
                            for r in recs)
        return hits, total

    @property
    def potion_hold_histogram(self) -> dict[str, int]:
        """All resolved instances (used/held/lost) binned by floors held."""
        bins = {"0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0}
        for r in self.potion_holds:
            h = r["held"]
            key = "0" if h <= 0 else "1" if h == 1 else "2-3" if h <= 3 else "4-6" if h <= 6 else "7+"
            bins[key] += 1
        return bins

    @property
    def card_take_counts(self) -> dict[str, tuple[int, int]]:
        """card class name -> (offered, taken), most-offered first."""
        return {name: (count, self.card_take_counts_raw.get(name, 0))
                for name, count in sorted(self.card_offer_counts.items(),
                                          key=lambda kv: (-kv[1], kv[0]))}

    @property
    def deck_histogram(self) -> list[tuple[str, str, int, float, float]]:
        """``(rarity, card, copies, share_of_rarity, copies_per_run)`` rows.

        Rarity blocks come out in COMMON/UNCOMMON/RARE order (the drop-tier
        order a reader expects, not the dict's insertion order); inside a
        block, cards descend by copies with ties broken on name so the export
        is deterministic.

        ``share_of_rarity`` is pooled over episodes like every other rate on
        this class -- copies / that rarity's total copies. ``copies_per_run``
        divides by ``episodes``; 0.0 rather than a ZeroDivisionError on a
        report built with no episodes.
        """
        order = ("common", "uncommon", "rare")
        rows: list[tuple[str, str, int, float, float]] = []
        for rarity in order:
            cards = self.deck_rarity_counts.get(rarity)
            if not cards:
                continue
            total = sum(cards.values())
            for name, copies in sorted(cards.items(), key=lambda kv: (-kv[1], kv[0])):
                rows.append((
                    rarity,
                    name,
                    copies,
                    copies / total if total else 0.0,
                    copies / self.episodes if self.episodes else 0.0,
                ))
        return rows

    @property
    def return_histogram(self) -> dict[float, int]:
        """Episode return -> how many episodes scored exactly it, ascending.

        An exact-value tally, not a binning: the configured reward range is
        small and integral enough (0-51) that the distinct returns ARE the
        buckets, and binning would blur genuinely distinct scores. Returns are
        rounded to 6dp first, so float noise (0.1 + 0.2 vs 0.3) folds into one
        bucket instead of splitting it."""
        hist: dict[float, int] = {}
        for value in self.returns:
            key = round(float(value), 6)
            hist[key] = hist.get(key, 0) + 1
        return dict(sorted(hist.items()))


def evaluate_run(
    policy: Policy,
    *,
    episodes: int = 20,
    seed: int = 0,
    env: Any | None = None,
    episode_seeds: "Sequence[int] | None" = None,
) -> RunEvalReport:
    """Roll ``policy`` over ``episodes`` seeded full runs (seed, seed+1, …).

    ``env`` defaults to a fresh ``STS2RunEnv``; pass an
    ``STS2CurriculumRunEnv`` to evaluate the phase-1 curriculum. Given the same
    seed and env settings this is deterministic: same episodes, same report.

    ``episode_seeds`` (v20.1, eval.py --random-episodes) overrides the
    sequential ``seed .. seed+episodes-1`` range with an explicit list —
    ``episodes``/``seed`` are ignored then, and the per-episode ``seeds``
    tuple in the report records exactly what ran (the CSV column too).
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
    seeds: list[int] = []
    returns: list[float] = []
    end_turns: list[int] = []
    energy_unspent: list[float] = []
    card_offers: list[int] = []
    card_takes: list[int] = []
    rest_visits: list[int] = []
    rest_heals: list[int] = []
    rest_upgrades: list[int] = []
    rest_visits_hihp: list[int] = []
    rest_upgrades_hihp: list[int] = []
    upgrades: list[int] = []
    removes: list[int] = []
    elites_won: list[int] = []
    elites_fought: list[int] = []
    potions_obtained: list[int] = []
    potions_used: list[int] = []
    potions_used_elite: list[int] = []
    potions_used_boss: list[int] = []
    potions_used_normal: list[int] = []
    potions_expired: list[int] = []
    potion_use_hp: list[float] = []
    potion_v_at_use: list[float] = []
    potions_wasted: list[int] = []
    potions_bought: list[int] = []
    potion_rewards_skipped: list[int] = []
    potion_rewards_forced: list[int] = []
    potion_relic_picks: list[int] = []
    potions_discarded: list[int] = []
    potion_skips: list[dict] = []
    card_offers_by_act: list[dict] = []
    card_takes_by_act: list[dict] = []
    relics: list[int] = []
    hp_lost: list[int] = []
    boss_hp_lost: list[int] = []
    hp_ratio_sum: list[float] = []
    hp_ratio_steps: list[int] = []
    card_offer_counts: dict[str, int] = {}
    card_take_counts: dict[str, int] = {}
    event_choice_counts: dict[tuple[str, str, str], int] = {}
    potion_holds: list[dict] = []
    deck_rarity_counts: dict[str, dict[str, int]] = {}

    # `mean_hp_overall`'s proxy signal (v8 s7 gate): the "run.hp_ratio" slot
    # of the observation the env already hands the policy each decision --
    # located once per env instance via its own layout, not a new env
    # counter. None on any env that doesn't expose one (e.g. a hand-rolled
    # test double), so the sampling below just no-ops.
    hp_ratio_slice = getattr(getattr(env, "_layout", None), "f_slices", {}).get("run.hp_ratio")

    seed_list = (list(episode_seeds) if episode_seeds is not None
                 else [seed + ep for ep in range(episodes)])
    episodes = len(seed_list)
    for ep_seed in seed_list:
        obs, info = env.reset(seed=ep_seed)
        max_floor = int(info.get("floor", 0))
        max_act = int(info.get("act", 0))
        steps = 0
        total_reward = 0.0
        hp_ratio_sum_ep = 0.0
        hp_ratio_steps_ep = 0
        terminated = truncated = False
        while not (terminated or truncated):
            if hp_ratio_slice is not None:
                hp_ratio_sum_ep += float(obs["f"][hp_ratio_slice][0])
                hp_ratio_steps_ep += 1
            mask = env.action_masks()
            action = int(policy(env, obs, mask))
            if not mask[action]:
                # Illegal pick → first legal action, so the eval can't stall.
                action = int(np.flatnonzero(mask)[0])
            obs, reward, terminated, truncated, info = env.step(action)
            steps += 1
            total_reward += float(reward)
            max_floor = max(max_floor, int(info.get("floor", 0)))
            max_act = max(max_act, int(info.get("act", 0)))

        hp_ratio_sum.append(hp_ratio_sum_ep)
        hp_ratio_steps.append(hp_ratio_steps_ep)
        floors.append(max_floor)
        acts.append(max_act)
        victories.append(bool(info.get("is_success", False)))
        hp_left.append(int(info.get("hp_left", 0)))
        decisions.append(int(info.get("decisions", steps)))
        trunc_flags.append(bool(truncated and not terminated))
        seeds.append(ep_seed)
        returns.append(total_reward)
        # Behavior tallies: present on the run envs (both terminated and
        # truncated episodes), absent on envs that don't count them — hence
        # the 0 defaults rather than a KeyError.
        end_turns.append(int(info.get("ep_end_turns", 0)))
        energy_unspent.append(float(info.get("ep_energy_unspent", 0.0)))
        card_offers.append(int(info.get("ep_card_offers", 0)))
        card_takes.append(int(info.get("ep_card_takes", 0)))
        rest_visits.append(int(info.get("ep_rest_visits", 0)))
        rest_heals.append(int(info.get("ep_rest_heals", 0)))
        rest_upgrades.append(int(info.get("ep_rest_upgrades", 0)))
        rest_visits_hihp.append(int(info.get("ep_rest_visits_hihp", 0)))
        rest_upgrades_hihp.append(int(info.get("ep_rest_upgrades_hihp", 0)))
        upgrades.append(int(info.get("ep_upgrades", 0)))
        removes.append(int(info.get("ep_removes", 0)))
        elites_won.append(int(info.get("ep_elites_won", 0)))
        elites_fought.append(int(info.get("ep_elites_fought", 0)))
        potions_obtained.append(int(info.get("ep_potions_obtained", 0)))
        potions_used.append(int(info.get("ep_potions_used", 0)))
        potions_used_elite.append(int(info.get("ep_potions_used_elite", 0)))
        potions_used_boss.append(int(info.get("ep_potions_used_boss", 0)))
        potions_used_normal.append(int(info.get("ep_potions_used_normal", 0)))
        potions_expired.append(int(info.get("ep_potions_expired", 0)))
        potion_use_hp.append(float(info.get("ep_potion_use_hp", 0.0)))
        potion_v_at_use.append(float(info.get("ep_potion_v_at_use", 0.0)))
        potions_wasted.append(int(info.get("ep_potions_wasted", 0)))
        potions_bought.append(int(info.get("ep_potions_bought", 0)))
        potion_rewards_skipped.append(int(info.get("ep_potion_rewards_skipped", 0)))
        potion_rewards_forced.append(int(info.get("ep_potion_rewards_forced", 0)))
        potion_relic_picks.append(int(info.get("ep_potion_relic_picks", 0)))
        potions_discarded.append(int(info.get("ep_potions_discarded", 0)))
        potion_skips.extend(info.get("ep_potion_skips", []))
        relics.append(int(info.get("ep_relics", 0)))
        hp_lost.append(int(info.get("ep_hp_lost", 0)))
        boss_hp_lost.append(int(info.get("ep_boss_hp_lost", 0)))
        for name, count in info.get("ep_card_offer_ids", {}).items():
            card_offer_counts[name] = card_offer_counts.get(name, 0) + int(count)
        for name, count in info.get("ep_card_take_ids", {}).items():
            card_take_counts[name] = card_take_counts.get(name, 0) + int(count)
        for key, count in info.get("ep_event_choices", {}).items():
            event_choice_counts[key] = event_choice_counts.get(key, 0) + int(count)
        # v23: tag each pooled hold record with its episode seed so
        # within-episode sequence reads (discard -> re-pickup) stay
        # computable after pooling.
        potion_holds.extend({**rec, "seed": ep_seed}
                            for rec in info.get("ep_potion_holds", []))
        card_offers_by_act.append(
            {int(k): int(v) for k, v in info.get("ep_card_offers_by_act", {}).items()})
        card_takes_by_act.append(
            {int(k): int(v) for k, v in info.get("ep_card_takes_by_act", {}).items()})
        for rarity, cards in info.get("ep_final_deck", {}).items():
            bucket = deck_rarity_counts.setdefault(rarity, {})
            for name, count in cards.items():
                bucket[name] = bucket.get(name, 0) + int(count)

    return RunEvalReport(
        episodes=episodes,
        floors=tuple(floors),
        acts=tuple(acts),
        victories=tuple(victories),
        truncations=tuple(trunc_flags),
        hp_left=tuple(hp_left),
        decisions=tuple(decisions),
        seeds=tuple(seeds),
        returns=tuple(returns),
        end_turns=tuple(end_turns),
        energy_unspent=tuple(energy_unspent),
        card_offers=tuple(card_offers),
        card_takes=tuple(card_takes),
        rest_visits=tuple(rest_visits),
        rest_heals=tuple(rest_heals),
        rest_upgrades=tuple(rest_upgrades),
        rest_visits_hihp=tuple(rest_visits_hihp),
        rest_upgrades_hihp=tuple(rest_upgrades_hihp),
        upgrades=tuple(upgrades),
        removes=tuple(removes),
        elites_won=tuple(elites_won),
        elites_fought=tuple(elites_fought),
        potions_obtained=tuple(potions_obtained),
        potions_used=tuple(potions_used),
        potions_used_elite=tuple(potions_used_elite),
        potions_used_boss=tuple(potions_used_boss),
        potions_used_normal=tuple(potions_used_normal),
        potions_expired=tuple(potions_expired),
        potion_use_hp=tuple(potion_use_hp),
        potion_v_at_use=tuple(potion_v_at_use),
        potions_wasted=tuple(potions_wasted),
        potions_bought=tuple(potions_bought),
        potion_rewards_skipped=tuple(potion_rewards_skipped),
        potion_rewards_forced=tuple(potion_rewards_forced),
        potion_relic_picks=tuple(potion_relic_picks),
        potions_discarded=tuple(potions_discarded),
        potion_skips=tuple(potion_skips),
        card_offers_by_act=tuple(card_offers_by_act),
        card_takes_by_act=tuple(card_takes_by_act),
        relics=tuple(relics),
        hp_lost=tuple(hp_lost),
        boss_hp_lost=tuple(boss_hp_lost),
        hp_ratio_sum=tuple(hp_ratio_sum),
        hp_ratio_steps=tuple(hp_ratio_steps),
        card_offer_counts=card_offer_counts,
        potion_holds=tuple(potion_holds),
        card_take_counts_raw=card_take_counts,
        deck_rarity_counts=deck_rarity_counts,
        event_choice_counts_raw=event_choice_counts,
    )


# ── Reporting: return histogram + spreadsheet export ─────────────────────────


EPISODE_CSV_FIELDS = ("policy", "seed", "floor", "act", "win", "truncated",
                      "hp_left", "decisions", "ep_return", "end_turns",
                      "energy_unspent", "card_offers", "card_takes",
                      "rest_visits", "rest_heals", "rest_upgrades",
                      "upgrades", "removes", "elites", "elites_fought",
                      "potions_got", "potions_used",
                      "potions_used_elite", "potions_used_boss",
                      "potions_used_normal", "potions_expired",
                      "potion_use_hp", "relics", "hp_lost",
                      # v8 s7 gate ("mean hp overall" proxy, see
                      # RunEvalReport.mean_hp_overall): mean run.hp_ratio
                      # over this episode's decisions.
                      "hp_ratio_mean",
                      "rest_visits_hihp", "rest_upgrades_hihp",
                      # v20 (Task 3b): appended at the END so existing
                      # column indices in downstream sheets stay valid.
                      "boss_hp_lost",
                      # v21: appended at the END (column indices stay valid).
                      "potion_v_at_use", "potions_wasted", "potions_bought",
                      "potion_rewards_skipped", "potion_rewards_forced",
                      "potion_relic_picks",
                      # v22: appended at the END (column indices stay valid).
                      "potions_discarded",
                      # v23: appended at the END — the per-act card-reward
                      # split (a1-a3 = 0-based act_index 0-2; report-only
                      # take-rate baseline, no guardrail).
                      "card_offers_a1", "card_takes_a1",
                      "card_offers_a2", "card_takes_a2",
                      "card_offers_a3", "card_takes_a3")

CARDS_CSV_FIELDS = ("policy", "card", "offered", "taken", "take_rate")

POTIONS_CSV_FIELDS = ("policy", "potion", "picked", "used", "held", "lost",
                      "discarded", "mean_hold_used", "mean_hold_all",
                      "v_at_use", "tier_share")

DECK_CSV_FIELDS = ("policy", "rarity", "card", "copies", "share_of_rarity",
                   "copies_per_run")

EVENTS_CSV_FIELDS = ("policy", "event", "page", "option", "chosen", "visits",
                     "pct")

HIST_CSV_FIELDS = ("policy", "ep_return", "count", "freq")

#: Longest bar in `reward_histogram_lines`, in characters.
HIST_BAR_WIDTH = 40


def reward_histogram_lines(name: str, report: RunEvalReport) -> list[str]:
    """ASCII bar chart of the episode-return distribution, one row per value.

    An exact-value tally (see `RunEvalReport.return_histogram`), so the row
    count is the number of distinct returns observed, not a fixed bin count.
    """
    hist = report.return_histogram
    # ASCII only: this goes to a Windows console under cp1252, where an em
    # dash comes out as a replacement character.
    lines = [f"return distribution - {name} ({report.episodes} episodes, "
             f"{len(hist)} distinct)"]
    if not hist:
        lines.append("  (no episodes)")
        return lines
    peak = max(hist.values())
    for value, count in hist.items():
        bar = "#" * max(1, round(HIST_BAR_WIDTH * count / peak))
        lines.append(f"  {value:>9.3f} {count:>6}  {count / report.episodes:>6.1%}  {bar}")
    return lines


def write_run_csv(
    path: str, rows: Sequence[tuple[str, RunEvalReport]]
) -> tuple[str, str]:
    """Export run-scale reports as two CSVs; returns (episodes_path, hist_path).

    Two files rather than one because they are two tables with different
    schemas — stacking them in one file would defeat the spreadsheet import
    they exist for. ``<stem>.episodes.csv`` is one row per episode per policy
    (raw data to pivot); ``<stem>.hist.csv`` is the return tally, already in
    chart-ready shape. A trailing ``.csv`` on ``path`` is stripped, so
    ``--csv out`` and ``--csv out.csv`` both yield ``out.episodes.csv``.

    Rows stay grouped by policy in input order, so a report with a baseline
    row sorts predictably in the sheet.
    """
    stem = path[:-4] if path.lower().endswith(".csv") else path
    ep_path, hist_path = f"{stem}.episodes.csv", f"{stem}.hist.csv"

    # Created on demand: these land in runs/run_logs/, which is gitignored and
    # so missing on a fresh clone -- and this runs *after* a long eval, too
    # late to be a tolerable place to fail.
    out_dir = os.path.dirname(ep_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(ep_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(EPISODE_CSV_FIELDS)
        for name, report in rows:
            for i in range(report.episodes):
                writer.writerow([
                    name,
                    report.seeds[i],
                    report.floors[i],
                    report.acts[i],
                    int(report.victories[i]),
                    int(report.truncations[i]),
                    report.hp_left[i],
                    report.decisions[i],
                    round(report.returns[i], 6),
                    # Guarded: a hand-built report (e.g. a unit test) may
                    # omit any of these tuples.
                    report.end_turns[i] if report.end_turns else 0,
                    report.energy_unspent[i] if report.energy_unspent else 0.0,
                    report.card_offers[i] if report.card_offers else 0,
                    report.card_takes[i] if report.card_takes else 0,
                    report.rest_visits[i] if report.rest_visits else 0,
                    report.rest_heals[i] if report.rest_heals else 0,
                    report.rest_upgrades[i] if report.rest_upgrades else 0,
                    report.upgrades[i] if report.upgrades else 0,
                    report.removes[i] if report.removes else 0,
                    report.elites_won[i] if report.elites_won else 0,
                    report.elites_fought[i] if report.elites_fought else 0,
                    report.potions_obtained[i] if report.potions_obtained else 0,
                    report.potions_used[i] if report.potions_used else 0,
                    report.potions_used_elite[i] if report.potions_used_elite else 0,
                    report.potions_used_boss[i] if report.potions_used_boss else 0,
                    report.potions_used_normal[i] if report.potions_used_normal else 0,
                    report.potions_expired[i] if report.potions_expired else 0,
                    report.potion_use_hp[i] if report.potion_use_hp else 0.0,
                    report.relics[i] if report.relics else 0,
                    report.hp_lost[i] if report.hp_lost else 0,
                    (report.hp_ratio_sum[i] / report.hp_ratio_steps[i]
                     if report.hp_ratio_steps and report.hp_ratio_steps[i] else 0.0),
                    report.rest_visits_hihp[i] if report.rest_visits_hihp else 0,
                    report.rest_upgrades_hihp[i] if report.rest_upgrades_hihp else 0,
                    report.boss_hp_lost[i] if report.boss_hp_lost else 0,
                    report.potion_v_at_use[i] if report.potion_v_at_use else 0.0,
                    report.potions_wasted[i] if report.potions_wasted else 0,
                    report.potions_bought[i] if report.potions_bought else 0,
                    report.potion_rewards_skipped[i] if report.potion_rewards_skipped else 0,
                    report.potion_rewards_forced[i] if report.potion_rewards_forced else 0,
                    report.potion_relic_picks[i] if report.potion_relic_picks else 0,
                    report.potions_discarded[i] if report.potions_discarded else 0,
                    *(n for act in (0, 1, 2) for n in (
                        report.card_offers_by_act[i].get(act, 0)
                        if report.card_offers_by_act else 0,
                        report.card_takes_by_act[i].get(act, 0)
                        if report.card_takes_by_act else 0)),
                ])

    with open(hist_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HIST_CSV_FIELDS)
        for name, report in rows:
            for value, count in report.return_histogram.items():
                freq = count / report.episodes if report.episodes else 0.0
                writer.writerow([name, value, count, round(freq, 6)])

    return ep_path, hist_path


def write_cards_csv(
    path_or_file, rows: Sequence[tuple[str, RunEvalReport]]
) -> None:
    """Per-card offer/take table (plan Task 8): one row per (policy, card
    class), most-offered first — the card-exposure / archetype-forcing signal.
    ``path_or_file`` is a filesystem path or an open text file."""
    def _write(fh) -> None:
        writer = csv.writer(fh)
        writer.writerow(CARDS_CSV_FIELDS)
        for name, report in rows:
            for card, (offered, taken) in report.card_take_counts.items():
                rate = round(taken / offered, 6) if offered else 0.0
                writer.writerow([name, card, offered, taken, rate])

    if hasattr(path_or_file, "write"):
        _write(path_or_file)
    else:
        with open(path_or_file, "w", newline="") as fh:
            _write(fh)


def write_potions_csv(
    path_or_file, rows: Sequence[tuple[str, RunEvalReport]]
) -> None:
    """Per-potion hold table (2026-08-23): one row per (policy, potion id),
    most-picked first — see ``RunEvalReport.potion_hold_table``.
    ``path_or_file`` is a filesystem path or an open text file."""
    def _write(fh) -> None:
        writer = csv.writer(fh)
        writer.writerow(POTIONS_CSV_FIELDS)
        for name, report in rows:
            for pid, t in report.potion_hold_table.items():
                writer.writerow([
                    name, pid, t["picked"], t["used"], t["held"], t["lost"],
                    t["discarded"],
                    round(t["mean_hold_used"], 6), round(t["mean_hold_all"], 6),
                    round(t["v_at_use"], 6), round(t["tier_share"], 6)])

    if hasattr(path_or_file, "write"):
        _write(path_or_file)
    else:
        with open(path_or_file, "w", newline="") as fh:
            _write(fh)


def write_events_csv(
    path_or_file, rows: Sequence[tuple[str, RunEvalReport]]
) -> None:
    """Per-event choice-percentage table: one row per (policy, event, page,
    option). ``visits`` is the total choices answered on that (event, page)
    and ``pct`` is chosen/visits, so each (event, page) group is its own
    100% split. Most-visited group first, most-chosen option first inside a
    group — each group reads as its own histogram.

    ``path_or_file`` is a filesystem path or an open text file, matching
    `write_cards_csv`."""
    def _write(fh) -> None:
        writer = csv.writer(fh)
        writer.writerow(EVENTS_CSV_FIELDS)
        for name, report in rows:
            visits: dict[tuple[str, str], int] = {}
            for (event, page, _option), count in report.event_choice_counts_raw.items():
                visits[(event, page)] = visits.get((event, page), 0) + count
            ordered = sorted(
                report.event_choice_counts_raw.items(),
                key=lambda kv: (-visits[(kv[0][0], kv[0][1])],
                                kv[0][0], kv[0][1], -kv[1], kv[0][2]))
            for (event, page, option), count in ordered:
                total = visits[(event, page)]
                pct = round(count / total, 6) if total else 0.0
                writer.writerow([name, event, page, option, count, total, pct])

    if hasattr(path_or_file, "write"):
        _write(path_or_file)
    else:
        with open(path_or_file, "w", newline="") as fh:
            _write(fh)


def write_deck_csv(
    path_or_file, rows: Sequence[tuple[str, RunEvalReport]]
) -> None:
    """Final-deck rarity census: one row per (policy, rarity, card).

    Rarity blocks in COMMON/UNCOMMON/RARE order, cards descending by copies
    inside each block (see `RunEvalReport.deck_histogram`) -- so each block
    reads as its own histogram and the whole file pivots in a spreadsheet.
    Starter, colorless, curse and quest cards were filtered out upstream in
    `sts2_rl.deck_stats`, and upgraded copies are folded into their base card.

    ``copies_per_run`` and ``share_of_rarity`` are pooled over ALL episodes
    including short ones, so a single long run contributes more copies than
    several early deaths and can dominate the profile.

    ``path_or_file`` is a filesystem path or an open text file, matching
    `write_cards_csv`."""
    def _write(fh) -> None:
        writer = csv.writer(fh)
        writer.writerow(DECK_CSV_FIELDS)
        for name, report in rows:
            for rarity, card, copies, share, per_run in report.deck_histogram:
                writer.writerow([name, rarity, card, copies,
                                 round(share, 6), round(per_run, 6)])

    if hasattr(path_or_file, "write"):
        _write(path_or_file)
    else:
        with open(path_or_file, "w", newline="") as fh:
            _write(fh)


# ── Paired-seed A/B ──────────────────────────────────────────────────────────


EVAL_SEEDS: tuple[int, ...] = tuple(range(1000, 1200))
"""Canonical fixed seed set for paired-seed A/B comparisons (phase 3 eval
rider). Any 200 seeds would do; this range just needs to be checked in once
so two comparisons run on the same seeds without re-deriving them."""


@dataclass(frozen=True)
class PairedRunDelta:
    """Per-seed outcomes of two policies on the SAME seed list, plus the
    minimal aggregates a CLI report needs. ``b`` is conventionally "new" /
    "candidate" and ``a`` is "baseline", so every delta is ``b - a``
    (positive = B did better)."""

    seeds: tuple[int, ...]
    floors_a: tuple[int, ...]
    floors_b: tuple[int, ...]
    wins_a: tuple[bool, ...]
    wins_b: tuple[bool, ...]
    hp_a: tuple[int, ...]
    hp_b: tuple[int, ...]

    @property
    def floor_deltas(self) -> tuple[int, ...]:
        return tuple(b - a for a, b in zip(self.floors_a, self.floors_b))

    @property
    def hp_deltas(self) -> tuple[int, ...]:
        return tuple(b - a for a, b in zip(self.hp_a, self.hp_b))

    @property
    def mean_floor_delta(self) -> float:
        return float(np.mean(self.floor_deltas)) if self.floor_deltas else 0.0

    @property
    def median_floor_delta(self) -> float:
        return float(np.median(self.floor_deltas)) if self.floor_deltas else 0.0

    @property
    def win_delta(self) -> int:
        """wins_b - wins_a, aggregate (not per-seed — a win is boolean)."""
        return sum(self.wins_b) - sum(self.wins_a)

    @property
    def better(self) -> int:
        """Seeds where B reached a strictly higher floor than A."""
        return sum(1 for d in self.floor_deltas if d > 0)

    @property
    def worse(self) -> int:
        return sum(1 for d in self.floor_deltas if d < 0)

    @property
    def tie(self) -> int:
        return sum(1 for d in self.floor_deltas if d == 0)


def compare_runs(
    policy_a: Callable[[], Policy],
    policy_b: Callable[[], Policy],
    *,
    seeds: Sequence[int] = EVAL_SEEDS,
    env_factory: Callable[[], Any] | None = None,
) -> PairedRunDelta:
    """Paired-seed A/B over the run-scale envs: both arms play the SAME
    seed list and the per-seed results are diffed.

    ``policy_a``/``policy_b`` are FACTORIES (``() -> Policy``), not policy
    instances. ``evaluate_run``'s determinism guarantee (inv-D §2,
    empirically verified) holds for one continuous sweep started from a
    *freshly constructed* policy — this function evaluates each arm as one
    such sweep across ``seeds`` (via repeated ``episodes=1`` calls, proven
    equivalent to a single ``episodes=len(seeds)`` call for a reused
    env+policy pair). If callers passed the *same policy instance* to both
    arms, a stateful policy would leak the first arm's RNG state into the
    second arm's identical-seed run — e.g. ``masked_random_policy``/
    ``masked_random_run_policy`` close over an RNG that advances every
    call, so re-using one instance for arm B would silently NOT reproduce
    arm A's per-seed sequence even under the same seed list. Factories sidestep
    that: pass ``lambda: masked_random_run_policy(random.Random(7))`` (fresh
    RNG per arm) or ``lambda: torch_policy(model, seed=7)`` (greedy
    ``TorchPolicy`` is stateless anyway; ``sample=True`` needs the fresh
    generator the factory gives it). The regression test below is exactly
    this contract: the SAME factory passed to both arms (each call producing
    an independently-seeded, behaviorally-identical policy) must yield zero
    deltas on every seed.

    ``env_factory`` defaults to a fresh ``STS2RunEnv()`` per arm (one env
    instance reused across that arm's ``seeds`` via ``reset()``, not
    recreated per seed — reset() fully reseeds, so this is behaviorally
    identical to a fresh env per seed but cheaper).
    """
    if env_factory is None:
        from .run_env import STS2RunEnv

        env_factory = STS2RunEnv

    def _sweep(make_policy: Callable[[], Policy]):
        policy = make_policy()
        env = env_factory()
        floors: list[int] = []
        wins: list[bool] = []
        hp: list[int] = []
        for s in seeds:
            report = evaluate_run(policy, episodes=1, seed=s, env=env)
            floors.append(report.floors[0])
            wins.append(report.victories[0])
            hp.append(report.hp_left[0])
        return tuple(floors), tuple(wins), tuple(hp)

    floors_a, wins_a, hp_a = _sweep(policy_a)
    floors_b, wins_b, hp_b = _sweep(policy_b)

    return PairedRunDelta(
        seeds=tuple(seeds),
        floors_a=floors_a, floors_b=floors_b,
        wins_a=wins_a, wins_b=wins_b,
        hp_a=hp_a, hp_b=hp_b,
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
