"""Tests for sts2_rl/run_probes.py (OBS_PLAN phase 3, Task 6 — run-scale
micro-probes). Mirrors test/test_pointer_run_decisions.py's own caution
around STS2RunEnv's known step() hang: every probe build/drive here is
bounded, seeded, and asserts loudly instead of looping unboundedly.

Oracle/anti-oracle policies are test-local and read env internals directly
(request.shop, request.rewards.cards, ...) — the anti-tautology gate the
brief calls for, proving each probe's `check` actually discriminates a
right answer from a wrong one instead of being trivially satisfiable.
"""
from __future__ import annotations

import numpy as np
import pytest

from sts2_rl.driver import DecisionKind
from sts2_rl.run_env import CHOICE_BASE, SELECT_BASE
from sts2_rl.run_probes import (
    RUN_PROBES,
    REWARD_ON_CURVE_ID,
    REWARD_OFFER_IDS,
    REWARD_TRAP_IDS,
    SHOP_REMOVAL_GOLD,
    SHOP_TRAP_GOLD,
    run_probe_accuracy,
    run_run_probe,
    run_run_probes,
)

# ═════════════════════════════════════════════════════════════════════════
# Shape
# ═════════════════════════════════════════════════════════════════════════


def test_at_least_three_probes():
    assert len(RUN_PROBES) >= 3


def test_probe_ids_are_unique():
    ids = [p.id for p in RUN_PROBES]
    assert len(ids) == len(set(ids))


# ═════════════════════════════════════════════════════════════════════════
# Determinism: build() twice -> identical first obs
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("probe", RUN_PROBES, ids=[p.id for p in RUN_PROBES])
def test_build_is_deterministic(probe):
    env_a = probe.build()
    env_b = probe.build()
    obs_a = env_a._build_obs()
    obs_b = env_b._build_obs()
    assert np.array_equal(obs_a["f"], obs_b["f"])
    assert np.array_equal(obs_a["i"], obs_b["i"])
    assert np.array_equal(env_a.action_masks(), env_b.action_masks())


# ═════════════════════════════════════════════════════════════════════════
# Oracle gate (anti-tautology): a scripted right answer scores 1.0, a
# scripted wrong-but-legal answer scores 0.0, probe by probe AND pooled.
# ═════════════════════════════════════════════════════════════════════════


def _scripted_oracle(env, obs, mask) -> int:
    """The one obviously-correct answer for whichever RUN_PROBES decision is
    currently parked, plus the minimum machinery to reach it (a which-card
    pick for the shop's removal sub-decision)."""
    request = env._request
    kind = request.kind
    if kind == DecisionKind.REST:
        return CHOICE_BASE + 0                       # heal
    if kind == DecisionKind.SHOP:
        entries = request.shop.all_entries
        return CHOICE_BASE + entries.index(request.shop.card_removal_entry)
    if kind == DecisionKind.SELECT_CARDS:
        return SELECT_BASE + 0                        # which card to remove
    if kind == DecisionKind.REWARD_CARD:
        ids = [c.id for c in request.rewards.cards]
        return CHOICE_BASE + ids.index(REWARD_ON_CURVE_ID)
    raise AssertionError(f"scripted_oracle: unexpected decision {kind!r}")


def _scripted_anti_oracle(env, obs, mask) -> int:
    """The deliberately wrong-but-legal answer at each probe's target
    decision; anything past that (e.g. map progress toward the next room,
    once the probe's outcome is already permanently unreachable) falls back
    to any legal action — the check can no longer become true either way."""
    request = env._request
    kind = request.kind
    if kind == DecisionKind.REST:
        return CHOICE_BASE + 2                        # leave, unhealed
    if kind == DecisionKind.SHOP:
        entries = request.shop.all_entries
        return CHOICE_BASE + len(entries)              # leave, nothing bought
    if kind == DecisionKind.REWARD_CARD:
        ids = [c.id for c in request.rewards.cards]
        return CHOICE_BASE + ids.index(REWARD_TRAP_IDS[0])   # take a trap
    return int(np.flatnonzero(mask)[0])


def test_oracle_scores_every_probe():
    for probe in RUN_PROBES:
        assert run_run_probe(probe, _scripted_oracle), probe.id


def test_anti_oracle_fails_every_probe():
    for probe in RUN_PROBES:
        assert not run_run_probe(probe, _scripted_anti_oracle), probe.id


def test_oracle_gate_accuracy():
    assert run_probe_accuracy(_scripted_oracle) == 1.0
    assert run_probe_accuracy(_scripted_anti_oracle) == 0.0


# ═════════════════════════════════════════════════════════════════════════
# run_run_probe contract: illegal action fails immediately; a policy that
# never resolves the decision fails by exhausting max_actions.
# ═════════════════════════════════════════════════════════════════════════


def test_illegal_action_fails_the_probe():
    def illegal_policy(env, obs, mask):
        illegal = np.flatnonzero(~mask)
        assert illegal.size, "expected at least one illegal action to exist"
        return int(illegal[0])

    probe = RUN_PROBES[0]
    assert run_run_probe(probe, illegal_policy) is False


def test_never_resolving_policy_fails_within_bound():
    # A policy that always answers "leave" the rest screen never satisfies
    # any RUN_PROBES check, and the map-progression fallback keeps handing
    # it decisions it CAN answer (never illegal) — so this proves the bound
    # itself terminates the probe, not an accidental illegal action.
    calls = {"n": 0}

    def wander(env, obs, mask):
        calls["n"] += 1
        request = env._request
        if request.kind == DecisionKind.REST:
            return CHOICE_BASE + 2
        return int(np.flatnonzero(mask)[0])

    probe = RUN_PROBES[0]
    assert run_run_probe(probe, wander, max_actions=5) is False
    assert calls["n"] <= 5


# ═════════════════════════════════════════════════════════════════════════
# run_run_probes / run_probe_accuracy aggregate correctly
# ═════════════════════════════════════════════════════════════════════════


def test_run_probes_and_accuracy_agree():
    results = run_run_probes(_scripted_oracle)
    assert results == [True] * len(RUN_PROBES)
    assert run_probe_accuracy(_scripted_oracle, RUN_PROBES) == 1.0


# ═════════════════════════════════════════════════════════════════════════
# Premise checks: the ordering claims the scenario design leans on
# (offer order == action index order; the shop's card-removal entry is NOT
# the lowest-indexed legal purchase) are asserted at build() time already
# (see run_probes.py), but pinned here too as an explicit, named premise —
# not something a probe redesign should silently stop guaranteeing.
# ═════════════════════════════════════════════════════════════════════════


def test_reward_offer_order_is_tuple_order_with_on_curve_in_the_middle():
    probe = next(p for p in RUN_PROBES if p.id == "card_reward_on_curve")
    env = probe.build()
    ids = [c.id for c in env._request.rewards.cards]
    assert ids == list(REWARD_OFFER_IDS)
    assert ids.index(REWARD_ON_CURVE_ID) not in (0, len(ids) - 1), (
        "on-curve pick must sit away from both index extremes"
    )


def test_shop_removal_is_not_the_lowest_legal_index():
    probe = next(p for p in RUN_PROBES if p.id == "shop_removal_dominant")
    env = probe.build()
    request = env._request
    entries = request.shop.all_entries
    removal_idx = entries.index(request.shop.card_removal_entry)
    legal = request.own_actions()
    assert len(legal) >= 2, "expected the trap plus the removal to both be legal"
    assert min(legal) != removal_idx, "removal must not be the lowest legal index"
    assert max(legal) != removal_idx, "removal must not be the highest legal index"
    # The affordability math the scenario leans on: one gold budget, can't
    # cover both the trap and the removal.
    assert SHOP_TRAP_GOLD + SHOP_REMOVAL_GOLD > SHOP_REMOVAL_GOLD > SHOP_TRAP_GOLD


# ═════════════════════════════════════════════════════════════════════════
# Anti-index-bias gate: neither "always pick the lowest legal action" nor
# "always pick the highest legal action" may ace the suite (the defect this
# fix lane closes — the previous scenarios put every correct answer at the
# lowest legal index of its screen, so `first_legal` scored 3/3).
# ═════════════════════════════════════════════════════════════════════════


def _first_legal(env, obs, mask) -> int:
    return int(np.flatnonzero(mask).min())


def _last_legal(env, obs, mask) -> int:
    return int(np.flatnonzero(mask).max())


def test_first_legal_policy_does_not_ace_the_suite():
    assert run_probe_accuracy(_first_legal) < 1.0


def test_last_legal_policy_does_not_ace_the_suite():
    assert run_probe_accuracy(_last_legal) < 1.0


def test_constant_index_policies_fail_the_reward_and_shop_probes():
    # The two probes this fix lane redesigned must each individually resist
    # both extremes — the aggregate gate above could in principle be
    # satisfied by one probe compensating for another.
    redesigned = [p for p in RUN_PROBES if p.id in ("shop_removal_dominant", "card_reward_on_curve")]
    for probe in redesigned:
        assert not run_run_probe(probe, _first_legal), f"{probe.id}: first-legal must not pass"
        assert not run_run_probe(probe, _last_legal), f"{probe.id}: last-legal must not pass"
