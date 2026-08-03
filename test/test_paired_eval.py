"""Tests for the paired-seed A/B layer (entity-obs-schema phase 3, Task 7).

``compare_runs`` reuses ``evaluate_run`` per seed (episodes=1) rather than
forking its episode loop — see ``sts2_rl.evaluation.compare_runs``'s
docstring for why policies are passed as FACTORIES (``() -> Policy``), not
instances: a stateful policy (e.g. ``masked_random_run_policy`` closes over
an RNG that advances every call) would leak arm A's RNG state into arm B's
identical-seed sweep if the same instance were reused for both arms.

Tests here use ``STS2CurriculumRunEnv(column_rooms=3)`` (the fast fixture
``test_eval_torch.py`` already uses) and tiny seed slices — never the full
200-seed ``EVAL_SEEDS``, never a real checkpoint, never GPU.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl.curriculum_env import STS2CurriculumRunEnv
from sts2_rl.evaluation import EVAL_SEEDS, PairedRunDelta, compare_runs
from sts2_rl.run_env import masked_random_run_policy

SEEDS = (5000, 5001, 5002, 5003)


def _env_factory():
    return STS2CurriculumRunEnv(column_rooms=3)


def _policy_factory(seed: int):
    return lambda: masked_random_run_policy(random.Random(seed))


# ── EVAL_SEEDS ────────────────────────────────────────────────────────────────


def test_eval_seeds_is_the_documented_fixed_range():
    assert EVAL_SEEDS == tuple(range(1000, 1200))
    assert len(EVAL_SEEDS) == 200


# ── compare_runs basics ───────────────────────────────────────────────────────


def test_compare_runs_shapes_and_types():
    delta = compare_runs(
        _policy_factory(1), _policy_factory(2),
        seeds=SEEDS, env_factory=_env_factory,
    )
    assert isinstance(delta, PairedRunDelta)
    assert delta.seeds == SEEDS
    for field in (delta.floors_a, delta.floors_b, delta.wins_a, delta.wins_b,
                  delta.hp_a, delta.hp_b):
        assert len(field) == len(SEEDS)
    assert all(isinstance(w, bool) for w in delta.wins_a + delta.wins_b)
    assert all(isinstance(f, int) for f in delta.floors_a + delta.floors_b)


def test_compare_runs_derived_properties_agree_with_raw_lists():
    delta = compare_runs(
        _policy_factory(3), _policy_factory(4),
        seeds=SEEDS, env_factory=_env_factory,
    )
    expected_floor_deltas = tuple(
        b - a for a, b in zip(delta.floors_a, delta.floors_b))
    assert delta.floor_deltas == expected_floor_deltas
    assert delta.hp_deltas == tuple(
        b - a for a, b in zip(delta.hp_a, delta.hp_b))
    assert delta.mean_floor_delta == pytest.approx(
        float(np.mean(delta.floor_deltas)))
    assert delta.median_floor_delta == pytest.approx(
        float(np.median(delta.floor_deltas)))
    assert delta.win_delta == sum(delta.wins_b) - sum(delta.wins_a)
    assert delta.better + delta.worse + delta.tie == len(SEEDS)
    assert delta.better == sum(1 for d in delta.floor_deltas if d > 0)
    assert delta.worse == sum(1 for d in delta.floor_deltas if d < 0)
    assert delta.tie == sum(1 for d in delta.floor_deltas if d == 0)


# ── Determinism / mutation-sensitive regression ──────────────────────────────


def test_compare_runs_same_policy_both_arms_is_all_zero_deltas():
    """The core invariant: pairing the SAME factory to both arms (each call
    building an independently-seeded but behaviorally-identical policy)
    must produce exactly zero deltas on every seed. This is also the
    mutation-sensitive test named in the brief — see
    scratchpad/p3-task-7-report.md for the monkeypatch that turns it RED
    when arm B's seeds are silently offset from arm A's."""
    factory = _policy_factory(42)
    delta = compare_runs(factory, factory, seeds=SEEDS, env_factory=_env_factory)

    assert delta.floors_a == delta.floors_b
    assert delta.wins_a == delta.wins_b
    assert delta.hp_a == delta.hp_b
    assert delta.floor_deltas == (0,) * len(SEEDS)
    assert delta.hp_deltas == (0,) * len(SEEDS)
    assert delta.mean_floor_delta == 0.0
    assert delta.median_floor_delta == 0.0
    assert delta.win_delta == 0
    assert delta.better == 0
    assert delta.worse == 0
    assert delta.tie == len(SEEDS)


def test_compare_runs_distinct_policies_can_diverge():
    """Sanity check the flip side of the zero-delta test: two policies with
    different RNG seeds are not artificially forced to tie (would mask a
    broken diff as easily as a false positive would)."""
    delta = compare_runs(
        _policy_factory(100), _policy_factory(999),
        seeds=tuple(range(6000, 6012)), env_factory=_env_factory,
    )
    # Not every seed need differ, but with 12 independent seeds and masked
    # random policies with different RNG streams, at least one should.
    assert delta.floors_a != delta.floors_b or delta.hp_a != delta.hp_b


# ── env_factory / seeds plumbing ──────────────────────────────────────────────


def test_compare_runs_seeds_override_is_honored_not_eval_seeds():
    """Passing a tiny ``seeds=`` must NOT fall back to the 200-seed default
    (that would make every test here slow and defeat the point of the
    override parameter)."""
    tiny = (7000, 7001)
    delta = compare_runs(
        _policy_factory(1), _policy_factory(1),
        seeds=tiny, env_factory=_env_factory,
    )
    assert delta.seeds == tiny
    assert len(delta.floors_a) == 2
