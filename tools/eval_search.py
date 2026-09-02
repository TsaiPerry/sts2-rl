"""eval_search.py — the Tier-B expectimax measurement (plan
2026-08-26-foresight-v25-v26, Task 9).

Answers ONE question with a number: how much does a one-ply expectimax
search over the policy's own top-k actions buy over the bare policy, on real
mid-run combats? Every fight in the bank is played THREE times from the SAME
`CombatFork` — same snapshot, same reset seed, same per-decision sampling
seeds — so the arms differ only in how each decision is chosen:

  * **policy arm** — the seeded sample from the policy's masked prior, start
    to finish. This is the agent as it actually acts (training sampled; a
    greedy-only baseline would measure a policy nobody deploys).
  * **greedy arm** — the prior ARGMAX at every decision, no rollouts. Exists
    to deconfound the gate: policy-vs-search folds greedy-vs-sampled into
    "search buys X points", so the pre-registered >=3pt gate could fire on
    the sampling difference alone. Greedy is the search arm with the search
    switched off — same action rule, same tie-break — so search-vs-greedy is
    the search's own contribution. It costs about what the policy arm costs
    (one forward per decision), so it always runs.
  * **search arm** — at every combat decision with more than one legal
    action, `forksim.expectimax` scores the top-k legal actions over m
    common-random-number branches and takes the best mean; single-legal-
    action decisions are taken without spending rollouts.

The report prints BOTH decompositions, labelled: search-vs-policy (the plan's
literal gate, confounded) and search-vs-greedy (the deconfounded read), plus
greedy-vs-policy (the confound itself).

Every arm stops the moment the fight resolves (`CombatFork.in_combat` goes
False), the episode ends, or the per-fight decision cap trips.

## Sharding and merging

`--shard i/n` runs `fights[i::n]`. Because fight `i` uses snapshot
`i % len(bank)`, a shard sees only snapshots congruent to `i` modulo
`gcd(n, len(bank))` — so at `gcd > 1` a SINGLE SHARD'S PRINTED RATES ARE
ALIASED (it may miss every boss snapshot) and must not be read alone. The
tool warns when this holds. Merged totals are unaffected: the shards together
are exactly the whole fight list.

`--json OUT.json` writes the per-arm ADDITIVE COUNTERS (numerators and
denominators — deaths, scored, unresolved, decisions, flips,
flips_vs_sample, survivors, hp_sum, rollouts, wall-clock sums) plus the
config. Never rates. Shards therefore merge by SUMMING the counters and
recomputing each rate once — averaging the shards' own rates would weight a
short shard equal to a long one. `--merge a.json b.json ...` does exactly
that and prints the combined report (and refuses files whose config disagrees
on anything that changes what was measured).

## Flip rate — what "flip" means here

The plan defines it as *search ≠ policy prior argmax*. That argmax is over
LEGAL actions, taken on the masked distribution (`model.action_logits`
mask-fills illegal actions before the softmax, so argmax over the whole
vector is already argmax over the legal ones) — i.e. exactly the action a
greedy `TorchPolicy` would emit at that state. It is deliberately NOT
"search ≠ the policy arm's sampled action": the sampled action is a draw, so
a flip against it would count the policy's own exploration noise as a
disagreement. The sampled comparison is still reported, as a secondary line,
because it bounds how much of the arms' behavioural gap is search versus
sampling.

Note the asymmetry this creates and does not hide: the policy arm SAMPLES
while the flip rate is measured against the ARGMAX. The two arms are
therefore not identical even at unflipped decisions. That is the plan's
design — the arms measure deployed-policy vs searched-policy outcomes, and
the flip rate separately measures how often the search has an opinion.

## Common random numbers

Within one decision the m salts (and the m rollout-policy seeds) are shared
by every candidate action — see `forksim.expectimax`. ACROSS decisions and
fights they must never collide, or two different decisions would be scored
against the same handful of stochastic futures and the search would inherit
a systematic bias from whichever futures those happened to be. The
derivations below are injective by construction (a positional encoding, not
a hash):

    salt(fight, d, j)          = (fight·MAX_DECISIONS + d)·m + j
    rollout_seed(fight, d, j)  = ROLLOUT_BASE + (fight·MAX_DECISIONS + d)·m + j
    act_seed(fight, d)         = ACT_BASE + fight·FIGHT_STRIDE + d

`fight` is the GLOBAL fight index, so `--shard` workers never share a salt
either. `d < MAX_DECISIONS` and `j < m` are asserted, which is what makes
the first two injective; `d < FIGHT_STRIDE` makes the third.

## Determinism

Given the same arguments the whole pipeline is reproducible: the fight list
is positional (no rng), each fight's reset seed is a function of `--seed`
and the fight index, and every sampling draw — arm actions and rollout
actions alike — is made from a generator reseeded from the derivations
above rather than from a shared, drifting one. Only the `[timing]` lines
vary between two runs of the same command.

Usage:
    eval_search.py CKPT --bank runs/snapshots/BANK.jsonl \
        --fights 150 --k 5 --m 8 [--asc 10] [--room elite,boss] \
        [--shard 0/8] [--json shard0.json]
    eval_search.py --merge shard*.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sts2_rl import forksim
from sts2_rl.evaluation import load_torch_policy
from sts2_rl.forksim import CombatFork
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.snapshots import act_module_for_encounter, load_snapshots

#: Per-fight decision cap. Doubles as the stride that makes the salt/rollout
#: seed derivations injective, so it is a CONSTANT, not a CLI knob: changing
#: it would silently renumber every salt.
MAX_DECISIONS = 512

#: Seed-space separators. Arbitrary high constants, far apart, so an arm's
#: sampling seed can never coincide with a rollout seed or a branch salt.
ACT_BASE = 0x51DE0000
ROLLOUT_BASE = 0x201F0000
FIGHT_STRIDE = 1_000_003

#: Search-noise seed separator. Added to the branch-salt and rollout-seed
#: bases so an independent --search-seed lands each gold run in a DISJOINT band
#: of salts (same decisions, independent rollouts) for the R-run consensus
#: truth (plan 2026-08-31-critic-value-fit). 1<<44 is far above any
#: _decision_index(fight,d)*m a real run reaches, so search_seed=0 is
#: byte-identical to the pre-search-seed derivations (backward compat).
SEARCH_SEED_STRIDE = 1 << 44


# ── seed derivations (see the module docstring) ─────────────────────────────


def _decision_index(fight: int, d: int) -> int:
    if not 0 <= d < MAX_DECISIONS:
        raise ValueError(f"decision index {d} outside [0, {MAX_DECISIONS})")
    return fight * MAX_DECISIONS + d


def _salt_base(fight: int, d: int, m: int, search_seed: int = 0) -> int:
    return _decision_index(fight, d) * m + search_seed * SEARCH_SEED_STRIDE


def _rollout_seed_base(fight: int, d: int, m: int, search_seed: int = 0) -> int:
    return ROLLOUT_BASE + _decision_index(fight, d) * m + search_seed * SEARCH_SEED_STRIDE


def _act_seed(fight: int, d: int) -> int:
    return ACT_BASE + fight * FIGHT_STRIDE + d


def _fight_seed(seed: int, fight: int) -> int:
    """The env reset seed for a fight — distinct per fight, and a pure
    function of `--seed` so a rerun (or another shard) reproduces it."""
    return seed * FIGHT_STRIDE + fight


# ── fight list ──────────────────────────────────────────────────────────────


def build_fight_list(bank_size: int, n_fights: int, seed: int) -> "list[tuple[int, int]]":
    """`[(snapshot_index, fight_seed)]`, one entry per fight.

    Deliberately positional rather than rng-sampled: cycling the (filtered)
    bank spreads the fights as evenly as possible over the available
    snapshots — with 9 snapshots and 150 fights every snapshot gets 16 or 17
    distinct seeds instead of a lumpy multinomial draw — and it makes the
    list a pure function of `(bank_size, n_fights, seed)`, which is what lets
    every `--shard` worker rebuild the identical global list and slice its
    own share out of it.
    """
    if bank_size <= 0:
        raise ValueError("build_fight_list: empty bank")
    return [(i % bank_size, _fight_seed(seed, i)) for i in range(n_fights)]


def parse_shard(text: "str | None") -> "tuple[int, int]":
    """`"i/n"` -> `(i, n)`; `None` -> `(0, 1)`."""
    if text is None:
        return 0, 1
    try:
        i_s, n_s = text.split("/")
        i, n = int(i_s), int(n_s)
    except ValueError:
        raise ValueError(f"--shard must look like i/n, got {text!r}") from None
    if n < 1 or not 0 <= i < n:
        raise ValueError(f"--shard {text!r}: need 0 <= i < n and n >= 1")
    return i, n


def shard_of(fights: "list", i: int, n: int) -> "list":
    """Every n-th fight starting at i — a stride slice, so the shards
    partition the list exactly and each one keeps its fights' GLOBAL indices
    (the caller pairs `enumerate(fights)` before sharding)."""
    return fights[i::n]


# ── one arm of one fight ────────────────────────────────────────────────────


@dataclass
class ArmResult:
    died: bool
    hp_out: int
    decisions: int
    searched: int = 0
    flips: int = 0
    flips_vs_sample: int = 0
    rollouts: int = 0
    unresolved: bool = False
    search_seconds: float = 0.0
    seconds: float = 0.0
    actions: "list[int]" = field(default_factory=list)


#: The three arms. `policy` is the deployed agent (seeded sample from the
#: prior); `greedy` is the same policy with the sampling removed (the prior
#: ARGMAX, the very action the flip rate is defined against, no rollouts);
#: `search` is greedy-plus-expectimax. The greedy arm exists to deconfound the
#: gate: policy-vs-search folds greedy-vs-sampled INTO "search buys X points",
#: so a >=3pt gate could fire on the sampling difference alone. With all three,
#: search-vs-policy is the plan's literal gate and search-vs-greedy is the
#: deconfounded read — search against a baseline that differs from it ONLY by
#: the search. It costs about what the policy arm costs (one forward per
#: decision, no rollouts), so it always runs.
ARMS = ("policy", "greedy", "search")


def play_fight(fork: CombatFork, policy, fight: int, *, mode: str,
               k: int, m: int, rollout_steps: int, gamma: float,
               device: str, mass_cap: "float | None" = None) -> ArmResult:
    """Play one fight from `fork` to its resolution and report the outcome.
    `mode` is one of `ARMS`.

    The live env is stepped forward in place while `actions` accumulates the
    same action list in parallel. Those are two views of one trajectory: the
    forksim contract is that `fork.replay(actions)` reproduces this env
    byte-for-byte (nothing here reseeds the live env — every branch gets its
    own fresh replay), which is exactly why the search can hand `actions` to
    `expectimax` as a prefix while the arm itself pays only one step per
    decision instead of a quadratic pile of replays.
    """
    if mode not in ARMS:
        raise ValueError(f"play_fight: mode must be one of {ARMS}, got {mode!r}")
    started = time.perf_counter()
    env = fork.replay([])
    actions: list[int] = []
    result = ArmResult(died=False, hp_out=0, decisions=0)
    d = 0
    truncated = False
    while d < MAX_DECISIONS and CombatFork.in_combat(env):
        if mode == "search":
            t0 = time.perf_counter()
            found = forksim.expectimax(
                fork, actions, policy, k, m, env=env,
                salt_base=_salt_base(fight, d, m),
                rollout_seed_base=_rollout_seed_base(fight, d, m),
                max_steps=rollout_steps, gamma=gamma, mass_cap=mass_cap)
            result.search_seconds += time.perf_counter() - t0
            action = found.action
            result.rollouts += found.n_rollouts
            if found.searched:
                result.searched += 1
                result.flips += int(found.flipped)
                # Secondary diagnostic only: what the policy arm's sampling
                # rule would have drawn at THIS state, so "search vs sample"
                # is comparable to "search vs argmax" on the same decision.
                probs, _mask = forksim.prior(policy, env)
                drawn = forksim.sample_from_prior(
                    probs, _act_seed(fight, d), device=device)
                result.flips_vs_sample += int(action != drawn)
        else:
            probs, mask = forksim.prior(policy, env)
            if mode == "greedy":
                # The prior argmax, restricted to legal ids and tie-broken by
                # ascending action id — the SAME rule `expectimax` uses for
                # `prior_argmax`, so the greedy arm is exactly "the search arm
                # with the search switched off" and their difference isolates
                # the search.
                action = forksim.top_k_actions(probs, mask, 1)[0]
            else:
                action = forksim.sample_from_prior(
                    probs, _act_seed(fight, d), device=device)

        _obs, _r, terminated, truncated, _info = env.step(int(action))
        actions.append(int(action))
        d += 1
        if terminated or truncated:
            break

    result.decisions = d
    result.actions = actions
    run_result = getattr(env, "_result", None)
    # Unresolved = the fight never reached an outcome, either way it can
    # happen: this tool's own decision cap, or the ENV's step cap truncating
    # the episode mid-fight (`truncated` with no `_result`). Both would
    # otherwise be scored as a survival at whatever HP the player happened to
    # be on, quietly flattering whichever arm ran longer.
    result.unresolved = ((d >= MAX_DECISIONS and CombatFork.in_combat(env))
                         or (truncated and run_result is None))
    # A run only ENDS mid-fight two ways: the player died, or the fight was
    # the act-4 boss and the run was won. `victory` separates them; a fight
    # that merely resolved leaves `_result` None and nobody died.
    result.died = run_result is not None and not bool(run_result.victory)
    result.hp_out = max(0, int(getattr(env._run, "hp", 0)))
    result.seconds = time.perf_counter() - started
    return result


# ── measurement ─────────────────────────────────────────────────────────────


@dataclass
class ArmTotals:
    """Every field is an additive counter — a numerator or a denominator,
    never a rate. That is what makes `--merge` correct: shard reports combine
    by SUMMING these and recomputing the rates once, whereas averaging the
    shards' own rates would weight a short shard equal to a long one."""

    fights: int = 0
    deaths: int = 0
    unresolved: int = 0
    survivors: int = 0
    hp_sum: int = 0
    decisions: int = 0
    seconds: float = 0.0
    # Search-arm only; zero everywhere else.
    searched: int = 0
    flips: int = 0
    flips_vs_sample: int = 0
    rollouts: int = 0
    search_seconds: float = 0.0

    FIELDS = ("fights", "deaths", "unresolved", "survivors", "hp_sum",
              "decisions", "seconds", "searched", "flips", "flips_vs_sample",
              "rollouts", "search_seconds")

    def add(self, arm: ArmResult) -> None:
        self.fights += 1
        self.decisions += arm.decisions
        self.seconds += arm.seconds
        self.searched += arm.searched
        self.flips += arm.flips
        self.flips_vs_sample += arm.flips_vs_sample
        self.rollouts += arm.rollouts
        self.search_seconds += arm.search_seconds
        if arm.unresolved:
            self.unresolved += 1
            return
        if arm.died:
            self.deaths += 1
        else:
            self.survivors += 1
            self.hp_sum += arm.hp_out

    def merge(self, other: "ArmTotals") -> None:
        for name in self.FIELDS:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def to_json(self) -> dict:
        return {name: getattr(self, name) for name in self.FIELDS}

    @classmethod
    def from_json(cls, obj: dict) -> "ArmTotals":
        return cls(**{name: obj[name] for name in cls.FIELDS})

    @property
    def scored(self) -> int:
        """Fights that actually resolved — the denominator for death rate.
        An unresolved fight (decision cap) is neither a death nor a
        survival and must not be averaged into either."""
        return self.fights - self.unresolved

    @property
    def death_rate(self) -> float:
        return self.deaths / self.scored if self.scored else float("nan")

    @property
    def mean_hp(self) -> float:
        """Mean hp_out among SURVIVORS. Beware: not comparable across arms
        whose death rates differ — an arm that dies in a fight drops that
        (low-HP) fight out of its own average, so dying more can raise this
        number. `mean_hp_all` is the comparable one."""
        return self.hp_sum / self.survivors if self.survivors else float("nan")

    @property
    def mean_hp_all(self) -> float:
        """Mean hp_out over every RESOLVED fight, a death counting as 0 —
        the survivorship-free version of `mean_hp`, and the one to compare
        across arms."""
        return self.hp_sum / self.scored if self.scored else float("nan")


def run_measurement(args) -> int:
    rooms = None
    if args.room:
        rooms = {r.strip().upper() for r in args.room.split(",") if r.strip()}

    bank = load_snapshots(args.bank)
    snaps = [bank[i] for i in range(len(bank))]
    total_loaded = len(snaps)
    # Event-launched encounters belong to no act module, so `CombatFork`
    # refuses them (it cannot force the act's RoomSet). Drop them here with a
    # count rather than crashing 40 fights into an overnight run.
    undrillable = [s for s in snaps if act_module_for_encounter(s.encounter_id) is None]
    snaps = [s for s in snaps if act_module_for_encounter(s.encounter_id) is not None]
    if rooms is not None:
        snaps = [s for s in snaps if s.room_type.upper() in rooms]
    if not snaps:
        print(f"eval_search: no usable snapshots in {args.bank} "
              f"(loaded {total_loaded}, rooms filter {sorted(rooms) if rooms else 'none'})")
        return 2

    env0 = STS2RunEnv(ascension=args.asc)
    policy, ckpt = load_torch_policy(args.ckpt, env_kind="run", env=env0,
                                     device=args.device, sample=True, seed=0)

    fights = list(enumerate(build_fight_list(len(snaps), args.fights, args.seed)))
    shard_i, shard_n = parse_shard(args.shard)
    mine = shard_of(fights, shard_i, shard_n)
    alias = shard_alias_warning(shard_n, len(snaps))

    from collections import Counter
    room_hist = Counter(s.room_type for s in snaps)

    print(f"ckpt {args.ckpt}")
    print(f"  schema {ckpt.get('obs_schema')}  arch {ckpt.get('arch')}")
    print(f"bank {args.bank}: {total_loaded} loaded, {len(snaps)} usable"
          f"{f', {len(undrillable)} event-launched dropped' if undrillable else ''}"
          f"  rooms {dict(sorted(room_hist.items()))}"
          f"  filter {sorted(rooms) if rooms else 'none'}")
    print(f"asc {args.asc}  k {args.k}  m {args.m}  "
          f"mass-cap {args.mass_cap if args.mass_cap is not None else 'off'}  "
          f"gamma {args.gamma}  "
          f"rollout-steps {args.rollout_steps}  seed {args.seed}")
    print(f"fights {args.fights} total, shard {shard_i}/{shard_n} -> "
          f"{len(mine)} this process")
    if alias:
        print(f"WARNING: {alias}")
    print()

    totals = {arm: ArmTotals() for arm in ARMS}

    for fight, (snap_idx, fight_seed) in mine:
        snap = snaps[snap_idx]
        fork = CombatFork(snap, seed=fight_seed, env_kwargs={"ascension": args.asc})
        # All three arms from the SAME fork: same snapshot, same reset seed,
        # same env_kwargs. They differ only in how each decision is chosen.
        run = {arm: play_fight(fork, policy, fight, mode=arm, k=args.k, m=args.m,
                               rollout_steps=args.rollout_steps, gamma=args.gamma,
                               device=args.device, mass_cap=args.mass_cap)
               for arm in ARMS}
        for arm in ARMS:
            totals[arm].add(run[arm])
        srh = run["search"]
        print(f"fight {fight:>4}  snap {snap_idx:>3} {snap.room_type:<7} "
              f"{snap.encounter_id:<26} seed {fight_seed:<12} | "
              + " | ".join(
                  f"{arm} hp {run[arm].hp_out:>3} died {int(run[arm].died)} "
                  f"d {run[arm].decisions:>3}" for arm in ARMS)
              + f" flips {srh.flips}/{srh.searched}"
              + ("  UNRESOLVED" if any(run[a].unresolved for a in ARMS) else ""))

    config = {
        "ckpt": args.ckpt, "bank": args.bank, "fights": args.fights,
        "k": args.k, "m": args.m, "mass_cap": args.mass_cap,
        "asc": args.asc, "room": args.room,
        "seed": args.seed, "gamma": args.gamma,
        "rollout_steps": args.rollout_steps, "device": args.device,
        "shard": f"{shard_i}/{shard_n}", "bank_usable": len(snaps),
    }
    print_report(totals, config, sharded=shard_n > 1, alias=alias)
    if args.json:
        write_json(args.json, totals, config)
        print(f"\nwrote {args.json}  "
              f"(merge shards with: eval_search.py --merge shard*.json)")
    return 0


# ── report / json ───────────────────────────────────────────────────────────


def print_report(totals: "dict[str, ArmTotals]", config: dict, *,
                 sharded: bool = False, alias: str = "") -> None:
    def pct(x: float) -> str:
        return "  n/a" if x != x else f"{x * 100:5.1f}%"

    pol, grd, srh = totals["policy"], totals["greedy"], totals["search"]
    searched, flips = srh.searched, srh.flips

    print()
    print("=" * 72)
    print("=== eval_search report ===")
    print("=" * 72)
    print(f"config  k {config['k']}  m {config['m']}  asc {config['asc']}  "
          f"seed {config['seed']}  shard {config['shard']}  "
          f"fights {config['fights']}  bank {config['bank']}")
    print(f"fights measured        {pol.fights}  (resolved: "
          + ", ".join(f"{a} {totals[a].scored}" for a in ARMS) + ")")
    print("decisions              "
          + "   ".join(f"{a} {totals[a].decisions}" for a in ARMS))
    print(f"decisions searched     {searched}   "
          f"(rollouts {srh.rollouts}; unsearched = single legal action)")
    flip_rate = flips / searched if searched else float("nan")
    samp_rate = srh.flips_vs_sample / searched if searched else float("nan")
    print(f"flip rate              {pct(flip_rate)}  "
          f"({flips}/{searched}, search != policy prior argmax)")
    print(f"  vs sampled action    {pct(samp_rate)}  "
          f"({srh.flips_vs_sample}/{searched}, secondary)")
    print()
    for arm in ARMS:
        t = totals[arm]
        print(f"death rate  {arm:<7}    {pct(t.death_rate)}  ({t.deaths}/{t.scored})")
    print()
    print("GATE decompositions (all three printed; do not read one alone):")
    print(f"  search vs policy     {pct(pol.death_rate - srh.death_rate)}  "
          f"= the plan's LITERAL gate (>= 3.0pts at flip rate >= 5%). Confounded: "
          f"the policy arm samples, so this folds greedy-vs-sampled in.")
    print(f"  search vs greedy     {pct(grd.death_rate - srh.death_rate)}  "
          f"= the DECONFOUNDED read. Greedy is the search arm with the search "
          f"switched off, so this is search alone.")
    print(f"  greedy vs policy     {pct(pol.death_rate - grd.death_rate)}  "
          f"= the confound itself (sampling vs argmax, zero rollouts).")
    print()
    for arm in ARMS:
        t = totals[arm]
        print(f"mean hp_out {arm:<7}    survivors {t.mean_hp:6.2f} (n {t.survivors})"
              f"   all resolved {t.mean_hp_all:6.2f} (n {t.scored}, deaths as 0)")
    print("  (survivors-only is survivorship-biased across arms with different "
          "death rates; compare 'all resolved')")
    if any(totals[a].unresolved for a in ARMS):
        print("unresolved (decision cap / env truncation): "
              + ", ".join(f"{a} {totals[a].unresolved}" for a in ARMS)
              + "  — excluded from every rate")
    if sharded:
        print("NOTE: this is ONE SHARD. Its printed rates are a biased sample of "
              "the fight list (see --shard); merge the --json files and read the "
              "merged report instead.")
        if alias:
            print(f"      {alias}")
    per_dec = srh.search_seconds / searched if searched else float("nan")
    print(f"[timing] search wall    {srh.search_seconds:8.2f}s over {searched} "
          f"searched decisions -> {per_dec:6.3f}s/decision")
    print("[timing] arm wall       "
          + "   ".join(f"{a} {totals[a].seconds:8.2f}s" for a in ARMS))
    print(f"[timing] per rollout    "
          f"{srh.search_seconds / srh.rollouts if srh.rollouts else float('nan'):.4f}s "
          f"({srh.rollouts} rollouts)")


#: Bumped whenever the json layout changes, so `--merge` refuses a stale
#: shard file rather than summing fields that mean something else.
JSON_SCHEMA = 1


def write_json(path, totals: "dict[str, ArmTotals]", config: dict) -> None:
    """Raw additive counters only — no rates. See `ArmTotals`'s docstring:
    shards merge by SUMMING these and recomputing the rates once."""
    payload = {
        "eval_search_schema": JSON_SCHEMA,
        "config": config,
        "arms": {arm: totals[arm].to_json() for arm in ARMS},
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def merge_json(paths: "list[str]") -> "tuple[dict[str, ArmTotals], dict]":
    """Sum the per-arm counters across shard files. Config keys that MUST
    match (they change what is being measured) are checked; `shard` is the
    one that is expected to differ and is replaced by a merged label.

    The shard labels are also CHECKED, not just concatenated: a shard index
    supplied twice would double-count that slice of the fight list (a silent
    wrong answer), so it is a hard error; a union that does not cover
    {0..n-1} means fights are MISSING from the merged totals, which is a
    biased-but-usable sample, so it warns on stderr instead."""
    totals = {arm: ArmTotals() for arm in ARMS}
    config: dict = {}
    shards: list[str] = []
    seen: dict[int, str] = {}
    shard_ns: set[int] = set()
    # mass_cap is absent from pre-cap shard files; .get() reads that as None,
    # which equals a new default-run shard's explicit None — correct, both
    # measured fixed-k search.
    must_match = ("ckpt", "bank", "fights", "k", "m", "mass_cap", "asc",
                  "room", "seed", "gamma", "rollout_steps", "device")
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        schema = payload.get("eval_search_schema")
        if schema != JSON_SCHEMA:
            raise ValueError(f"{path}: eval_search_schema {schema!r}, "
                             f"expected {JSON_SCHEMA}")
        cfg = payload["config"]
        if not config:
            config = dict(cfg)
        else:
            bad = [key for key in must_match if cfg.get(key) != config.get(key)]
            if bad:
                raise ValueError(
                    f"{path}: config disagrees with the first file on {bad} — "
                    f"these shards did not measure the same thing")
        label = str(cfg.get("shard"))
        shards.append(label)
        idx = n = None
        if "/" in label:
            head, _, tail = label.partition("/")
            try:
                idx, n = int(head), int(tail)
            except ValueError:
                idx = n = None
        if idx is None:
            print(f"WARNING: {path}: unparseable shard label {label!r} — "
                  f"cannot check shard coverage", file=sys.stderr)
        else:
            if idx in seen:
                raise ValueError(
                    f"{path}: shard {label} was already merged from "
                    f"{seen[idx]} — merging it twice would double-count that "
                    f"slice of the fight list")
            seen[idx] = path
            shard_ns.add(n)
        for arm in ARMS:
            totals[arm].merge(ArmTotals.from_json(payload["arms"][arm]))
    if len(shard_ns) > 1:
        print(f"WARNING: shard files disagree on the shard count n "
              f"({sorted(shard_ns)}) — coverage cannot be checked",
              file=sys.stderr)
    elif shard_ns:
        n = next(iter(shard_ns))
        missing = sorted(set(range(n)) - set(seen))
        if missing:
            print(f"WARNING: incomplete merge — shard indices {missing} of "
                  f"n={n} are missing; the merged totals cover only "
                  f"{len(seen)}/{n} of the fight list", file=sys.stderr)
    config["shard"] = "merged(" + ",".join(shards) + ")"
    return totals, config


def shard_alias_warning(shard_n: int, bank_size: int) -> str:
    """Non-empty when a single shard's fights cannot cover the whole bank.

    Fight `i` uses snapshot `i % bank_size` and shard `i` takes `fights[i::n]`,
    so shard `i` only ever sees snapshots congruent to `i` modulo
    `g = gcd(n, bank_size)` — `bank_size // g` of them. At g > 1 a shard's own
    rates are computed over a biased slice of the bank (it may miss every boss
    snapshot, say) and must never be read alone; the MERGED report is still
    exactly right, because the shards together are the whole fight list.
    """
    from math import gcd

    g = gcd(shard_n, bank_size)
    if shard_n <= 1 or g <= 1:
        return ""
    return (f"shard aliasing: gcd(n={shard_n}, snapshots={bank_size}) = {g}, so "
            f"each shard sees only {bank_size // g}/{bank_size} snapshots. Merged "
            f"totals are unaffected; a single shard's rates are NOT "
            f"representative. Use an n coprime with {bank_size} to avoid it.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ckpt", nargs="?", help="checkpoint (omit only with --merge)")
    ap.add_argument("--bank", help="snapshot bank JSONL (required to measure)")
    ap.add_argument("--json", default=None, metavar="OUT.json",
                    help="also write the raw additive counters (per arm) plus "
                         "the config, so sharded runs can be merged")
    ap.add_argument("--merge", nargs="+", default=None, metavar="SHARD.json",
                    help="merge --json files from a sharded run and print the "
                         "combined report; measures nothing")
    ap.add_argument("--fights", type=int, default=150)
    ap.add_argument("--k", type=int, default=5, help="candidate actions per decision")
    ap.add_argument("--m", type=int, default=8, help="branches (salts) per candidate")
    ap.add_argument("--mass-cap", type=float, default=None,
                    help="adaptive breadth: shrink the top-k candidate set to "
                         "the smallest prefix covering this prior mass "
                         "(clamped to [2, k]); default off = fixed k")
    ap.add_argument("--asc", type=int, default=10, help="ascension the drill env runs at")
    ap.add_argument("--room", default=None,
                    help="comma-separated room types to keep, e.g. elite,boss "
                         "(default: every room type in the bank)")
    ap.add_argument("--shard", default=None, metavar="I/N",
                    help="run only every N-th fight starting at I — for "
                         "parallelising the overnight run across processes. A "
                         "single shard's printed rates are ALIASED whenever "
                         "gcd(N, snapshots) > 1 and must not be read alone: "
                         "write --json per shard and read the --merge report")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rollout-steps", type=int, default=120,
                    help="max steps in a search rollout (forksim default 120)")
    ap.add_argument("--gamma", type=float, default=0.999)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)

    if args.merge:
        totals, config = merge_json(args.merge)
        print(f"merged {len(args.merge)} shard file(s): {', '.join(args.merge)}")
        print_report(totals, config)
        return 0
    if not args.ckpt or not args.bank:
        ap.error("a checkpoint and --bank are required (unless --merge)")
    return run_measurement(args)


if __name__ == "__main__":
    raise SystemExit(main())
