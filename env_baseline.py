"""Absolute sanity floors for the training envs — gross-breakage detection.

Read `prompts/entity-obs-schema.md`, "Measurement", before changing anything
here. **This tool deliberately has no before/after mode.** An earlier version
had one; it was struck, and re-introducing it would be a mistake, not an
improvement:

    The phase-1 riders change the action layout (R4's candidate-index block),
    the observation contents (R1/R2/R3) and the encodings (R6); phase 2
    changes how actions are scored (R8/R9). A delta across that many
    simultaneous changes attributes nothing. That holds even for a
    policy-free measurement, because a masked-random policy over a *different
    action space* samples a different distribution — so "same seed, same
    result" is not a property the restructure should have, and asserting it
    would be asserting something false.

What survives is validation against **engine ground truth**, which does not
care what the encoding is. This module is the coarse half of that: a
masked-random sweep read as absolute thresholds — runs complete, floors land
in a plausible band, every decision kind that should be reachable is reached,
and no mask silently collapses a decision. The fine half is the
observation-content assertions (decode the obs, compare against direct
`CombatState` / `RunState` reads), which live in the test suite.

    py env_baseline.py sanity --env column --seeds 300
    py env_baseline.py sanity --env combat --seeds 300 --out runs/combat.sanity.json

Exit code is 0 only if every threshold passes.

The run-env hang
----------------
`env.step()` on the run env has been observed hanging indefinitely inside a
single call. `--step-timeout` arms `faulthandler.dump_traceback_later` per
episode, so a wedged episode prints the spinning greenlet's frames and exits
non-zero rather than stalling forever. That is detection, not mitigation: no
timed-out episode contributes a statistic, and the hang itself belongs to the
source-fidelity audit.
"""
from __future__ import annotations

import argparse
import collections
import faulthandler
import json
import random
import statistics
import sys
from typing import Any

import numpy as np

# ── Absolute thresholds ──────────────────────────────────────────────────
# Deliberately WIDE. These catch gross breakage — a dead mask, a zeroed
# reward, an unreachable phase, an env that no longer terminates. They are not
# regression detectors and must never be tightened into one: a threshold tight
# enough to catch a regression is a threshold that fails on ordinary variance,
# and this project has no controlled comparison to calibrate it against.
#
# The bands are anchored on the pre-restructure measurement (column/run:
# floor mean ~4.6, max 13; combat: ~57% masked-random win rate) and then
# opened up generously in both directions.
RUN_FLOOR_MEAN_BAND = (1.0, 30.0)
RUN_FLOOR_MAX_MIN = 6            # at least one episode must get somewhere
COMBAT_WIN_RATE_BAND = (0.15, 0.95)

# Decision kinds a masked-random sweep reliably reaches, and therefore the
# only ones it is fair to ASSERT. Measured 2026-08-01 over 40 column seeds:
# map, combat, event, reward_card, reward_potion, select_cards, select_option,
# shop and rest were all hit.
#
# `reward_relic` was not, and the reason is rarity rather than breakage: it is
# raised only by `RunDriver._reward_selector` (driver.py:414-417), whose
# callers all require the player to ALREADY hold a specific relic (Calling
# Bell, Black Star, Lava Rock, Toy Box, Small Capsule) or to hit one of two
# events (Crystal Sphere, War Historian Repy). Random play in act 0 seldom
# gets any of them.
#
# It is deliberately reported-not-asserted, and this set is a FLOOR that should
# be raised, not a permanent exclusion list: once a policy reaches deeper acts
# — or once the concurrent source-fidelity audit lands whatever it changes —
# more kinds become reliably reachable and belong in here. `report()` prints
# every kind that was reached and every declared kind that was not, so the gap
# stays visible instead of being silently normalised.
REQUIRED_DECISION_KINDS = frozenset({
    "map", "combat", "event", "reward_card", "select_cards",
})


def build_env(kind: str, card_obs: str = "hybrid"):
    if kind == "column":
        from sts2_rl.curriculum_env import STS2CurriculumRunEnv

        return STS2CurriculumRunEnv(card_obs=card_obs)
    if kind == "run":
        from sts2_rl.run_env import STS2RunEnv

        return STS2RunEnv(card_obs=card_obs)
    if kind == "combat":
        from sts2_rl.full_env import STS2FullCombatEnv

        return STS2FullCombatEnv(card_obs=card_obs)
    raise SystemExit(f"unknown --env {kind!r} (column | run | combat)")


def obs_size(obs: Any) -> tuple[int, int]:
    """(elements, bytes) for either observation contract — a flat float array
    before phase 1, a {"f": float32, "i": int32} dict after. Recorded as an
    absolute figure; there is nothing to compare it to."""
    arrays = ([np.asarray(v) for v in obs.values()] if isinstance(obs, dict)
              else [np.asarray(obs)])
    return (sum(int(a.size) for a in arrays),
            sum(int(a.nbytes) for a in arrays))


def candidate_signature(card) -> tuple:
    """What makes two select-candidates genuinely different to a player.

    This is the R4 question made precise. The run env answers a SELECT_CARDS
    decision with a `(card id, upgraded)` pair, so two candidates sharing that
    pair collapse onto one action. Collapsing two *identical* cards loses
    nothing — picking either has the same outcome. Collapsing two cards that
    differ in enchantment, affliction or cost modifier is an outright wrong
    answer: the agent can see two distinct options and address only one.

    So the mask check below compares distinct SIGNATURES against mask bits,
    not option count against mask bits. Measured 2026-08-01 on the pre-R4 env:
    forced-single-action select decisions do occur (3 identical `defend`s
    offered as 3 options with 1 mask bit), but every observed case was the
    benign kind.
    """
    ench = getattr(card, "enchantment", None)
    affl = getattr(card, "affliction", None)
    return (
        card.id,
        card.upgrade_level,
        getattr(ench, "id", None),
        getattr(affl, "id", None),
        getattr(affl, "amount", 0) if affl is not None else 0,
        card.energy_cost,
    )


def play_episode(env, seed: int, max_steps: int, stats: dict) -> dict[str, Any]:
    """One masked-random episode, accumulating sanity observations into
    ``stats`` (shared across the sweep)."""
    rng = random.Random(seed)
    obs, _ = env.reset(seed=seed)
    floats, nbytes = obs_size(obs)

    total_reward = 0.0
    decisions = 0
    max_floor = 0
    max_act = 0
    info: dict = {}
    completed = False

    for _ in range(max_steps):
        request = getattr(env, "_request", None)
        mask = np.asarray(env.action_masks())
        legal = np.flatnonzero(mask)

        if legal.size == 0:
            stats["dead_masks"].append(seed)
            break
        if request is not None:
            stats["kinds"][request.kind.value] += 1
            _check_mask(request, int(mask.sum()), seed, stats)

        obs, reward, terminated, truncated, info = env.step(int(rng.choice(legal)))
        decisions += 1
        total_reward += float(reward)
        max_floor = max(max_floor, int(info.get("floor", 0)))
        max_act = max(max_act, int(info.get("act", 0)))
        if terminated or truncated:
            completed = True
            break

    return {
        "seed": seed,
        "decisions": decisions,
        "reward": round(total_reward, 6),
        "max_floor": max_floor,
        "max_act": max_act,
        "victory": bool(info.get("is_success", False)),
        "completed": completed,
        "obs_floats": floats,
        "obs_bytes": nbytes,
    }


def _check_mask(request, n_mask_bits: int, seed: int, stats: dict) -> None:
    """Flag a decision the mask cannot fully express.

    For SELECT_CARDS this compares distinct candidate *signatures* to mask
    bits — see `candidate_signature`. For every other kind the options are
    already positional, so option count is the right comparison."""
    kind = request.kind.value
    if kind == "select_cards":
        n_distinct = len({candidate_signature(c) for c in request.candidates})
        if request.skippable:
            n_distinct += 1
        if n_distinct > n_mask_bits:
            stats["unaddressable"].append(
                {"seed": seed, "kind": kind, "purpose": request.purpose,
                 "distinct": n_distinct, "mask_bits": n_mask_bits})
        return
    n_opts = len(request.own_actions()) + len(request.potion_actions())
    if n_opts >= 2 and n_mask_bits == 1:
        stats["forced"].append({"seed": seed, "kind": kind, "options": n_opts})


def sanity(args: argparse.Namespace) -> None:
    env = build_env(args.env, args.card_obs)
    stats: dict[str, Any] = {
        "kinds": collections.Counter(),
        "unaddressable": [],
        "forced": [],
        "dead_masks": [],
    }
    episodes: list[dict[str, Any]] = []
    try:
        for seed in range(args.seeds):
            if args.step_timeout:
                faulthandler.dump_traceback_later(
                    args.step_timeout, repeat=False, exit=True)
            try:
                episodes.append(play_episode(env, seed, args.max_steps, stats))
            finally:
                if args.step_timeout:
                    faulthandler.cancel_dump_traceback_later()
            if (seed + 1) % 50 == 0:
                print(f"  {seed + 1}/{args.seeds} episodes", flush=True)
    finally:
        env.close()

    failures = report(args.env, episodes, stats)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"env": args.env, "episodes": episodes,
                       "kinds": dict(stats["kinds"])}, f, indent=1)
            f.write("\n")
        print(f"\nWrote {args.out}")
    if failures:
        print(f"\nFAILED {len(failures)} sanity threshold(s):")
        for line in failures:
            print(f"  - {line}")
        raise SystemExit(1)
    print("\nAll sanity thresholds passed.")


def report(env_kind: str, episodes: list[dict[str, Any]],
           stats: dict) -> list[str]:
    floors = [e["max_floor"] for e in episodes]
    decisions = [e["decisions"] for e in episodes]
    rewards = [e["reward"] for e in episodes]
    wins = sum(1 for e in episodes if e["victory"])
    win_rate = wins / max(1, len(episodes))
    floor_mean = statistics.fmean(floors)
    incomplete = [e["seed"] for e in episodes if not e["completed"]]

    print(f"\n=== {env_kind}: {len(episodes)} masked-random episodes ===")
    print(f"observation      {episodes[0]['obs_floats']} elements / "
          f"{episodes[0]['obs_bytes']} bytes")
    print(f"win rate         {win_rate:.3f}")
    print(f"floor            mean {floor_mean:.2f}  median "
          f"{statistics.median(floors)}  max {max(floors)}")
    print(f"decisions/ep     mean {statistics.fmean(decisions):.2f}")
    print(f"reward/ep        mean {statistics.fmean(rewards):.4f}")
    print(f"decision kinds   {dict(stats['kinds'])}")
    if env_kind != "combat":
        from sts2_rl.driver import DecisionKind

        never = sorted({k.value for k in DecisionKind} - set(stats["kinds"]))
        if never:
            # Printed, not failed: an unreached kind is usually rarity (see
            # REQUIRED_DECISION_KINDS). Kept visible so it cannot quietly
            # become permanent.
            print(f"NEVER REACHED    {never}   <- rarity, or a real gap; "
                  f"do not normalise silently")

    failures: list[str] = []
    if incomplete:
        failures.append(
            f"{len(incomplete)} episode(s) neither terminated nor truncated "
            f"within the step budget: seeds {incomplete[:10]}")
    if stats["dead_masks"]:
        failures.append(
            f"{len(stats['dead_masks'])} step(s) offered ZERO legal actions: "
            f"seeds {stats['dead_masks'][:10]}")
    if all(r == 0.0 for r in rewards):
        failures.append("every episode scored exactly 0 reward — reward wiring is dead")

    # Only the run-scale envs have decisions: STS2FullCombatEnv drives a
    # CombatState directly and has no DecisionRequest at all, so an empty
    # kinds counter is correct there rather than a failure.
    if env_kind != "combat":
        missing = REQUIRED_DECISION_KINDS - set(stats["kinds"])
        if missing:
            failures.append(f"decision kinds never reached: {sorted(missing)}")

    if stats["unaddressable"]:
        n = len(stats["unaddressable"])
        example = stats["unaddressable"][0]
        failures.append(
            f"{n} decision(s) offered more distinct candidates than the mask "
            f"can address — R4's collapse, information-losing variety. "
            f"EXPECTED TO FAIL until R4 (candidate-index action block) lands; "
            f"it must pass afterwards, and this is R4's acceptance test. "
            f"First: {example}")
    if stats["forced"]:
        print(f"\nnote: {len(stats['forced'])} non-select decision(s) with >=2 "
              f"options had a single legal action; first: {stats['forced'][0]}")

    if env_kind == "combat":
        lo, hi = COMBAT_WIN_RATE_BAND
        if not lo <= win_rate <= hi:
            failures.append(
                f"masked-random win rate {win_rate:.3f} outside the sanity "
                f"band [{lo}, {hi}]")
    else:
        lo, hi = RUN_FLOOR_MEAN_BAND
        if not lo <= floor_mean <= hi:
            failures.append(
                f"mean floor {floor_mean:.2f} outside the sanity band "
                f"[{lo}, {hi}]")
        if max(floors) < RUN_FLOOR_MAX_MIN:
            failures.append(
                f"best floor across all seeds is {max(floors)}, below the "
                f"sanity minimum {RUN_FLOOR_MAX_MIN}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sanity")
    s.add_argument("--env", default="column", choices=["column", "run", "combat"])
    s.add_argument("--card-obs", default="hybrid", choices=["hybrid", "features"])
    s.add_argument("--seeds", type=int, default=300)
    s.add_argument("--max-steps", type=int, default=20_000)
    s.add_argument("--step-timeout", type=int, default=300,
                   help="seconds before a wedged episode dumps its stack and "
                        "exits; 0 disables (default 300)")
    s.add_argument("--out", default=None)
    s.set_defaults(func=sanity)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
