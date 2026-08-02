"""Buffer-safety tests for the v4/v7 observation builders
(prompts/entity-obs-schema.md).

**What this file used to be** (v3): a reference-equality harness. It froze
the pre-vectorization pure-Python builders (``_ref_*``) as an oracle and
asserted, over seeded episodes, that the live vectorized ``ObsBuffer``-based
builders matched them bit-for-bit. Phase 1 replaced the whole observation
representation (dense per-vocab-id float blocks -> sparse id/float row
blocks over a two-leaf ``{"f", "i"}`` Dict, OBS_SCHEMA.md Sec.2/Sec.5), so
those frozen references no longer describe anything real — ``power_triples``,
``pile_composition``, ``ENEMY_ROW_DIM`` and the flat-Box builders they were
written against are gone, not renamed. Reference-equality against a v3 oracle
is retired: there is no meaningful "old shape" left to compare against.

**What survives**, per the project brief: this file's real job was never the
literal reference comparison, it was catching a reused-buffer/aliasing class
of bug that a same-shape-and-close-enough-values test would miss. Two
concrete instances of that class still exist in this codebase and are both
still worth pinning:

1. ``STS2FullCombatEnv``/``build_combat_obs`` allocate a fresh ``ObsBuffer``
   per call but still promise callers independent copies (their own
   docstrings) — a caller mutating one returned observation must never affect
   a previously returned one.
2. ``STS2RunEnv`` keeps ONE ``ObsBuffer`` for the WHOLE episode, reset() and
   rewritten every step (``STS2RunEnv._build_obs``'s own docstring names the
   exact hazard: "a block that is not live this step ... is exactly that:
   PAD/zero, never stale content from a previous step"). This is the
   highest-value surviving property in this file, and nothing in
   ``test_run_obs_v4.py`` drives an actual multi-phase episode to check it —
   that file's tests are unit-style (surgically set ``env._request`` and call
   ``_build_obs()`` once), so a leak that only shows up ACROSS a phase
   transition would slip past it.

Run with:  py -m pytest test/test_obs_vectorization.py -q
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl import STS2FullCombatEnv
from sts2_rl.driver import DecisionKind
from sts2_rl.full_env import DEFAULT_ENCOUNTERS, build_combat_obs, combat_obs_layout
from sts2_rl.run_env import (
    MAP_SLOTS,
    STS2RunEnv,
    masked_random_run_policy,
    run_obs_layout,
)


# ═════════════════════════════════════════════════════════════════════════
# 1. STS2FullCombatEnv / build_combat_obs: independent copies
# ═════════════════════════════════════════════════════════════════════════


def test_full_env_step_returns_independent_copy():
    """step()/reset() must never alias a mutable internal buffer — two stored
    observations must not change under one another. Both halves of the Dict
    are checked, not just "f" (a wrapper bug fixed elsewhere in this project
    copied "f" but forgot "i" — see test_combat_obs_v4.py's
    test_ablated_obs_env_copies_both_halves_not_just_f — so the same mistake
    is worth guarding at the raw env level too)."""
    env = STS2FullCombatEnv(deck=["strike", "defend", "bash"])
    obs1, _ = env.reset(seed=0)
    f1_snapshot, i1_snapshot = obs1["f"].copy(), obs1["i"].copy()
    mask = env.action_masks()
    obs2, *_ = env.step(int(np.flatnonzero(mask)[0]))
    obs2["f"][:] = -1.0
    obs2["i"][:] = 999_999
    np.testing.assert_array_equal(obs1["f"], f1_snapshot)
    np.testing.assert_array_equal(obs1["i"], i1_snapshot)
    assert obs1 is not obs2
    assert not np.shares_memory(obs1["f"], obs2["f"])
    assert not np.shares_memory(obs1["i"], obs2["i"])


def test_build_combat_obs_is_a_pure_deterministic_function_of_state():
    """The reference-equality harness this file used to run drove hundreds of
    states through both a frozen reference and the live builder to catch any
    drift; the frozen reference is gone, but the property that made that
    harness meaningful — building the observation is a pure function of the
    CombatState, with no incidental randomness or accumulating side effect on
    a reused buffer — still exists and is directly checkable: calling
    build_combat_obs twice on the same unchanged state must produce
    byte-identical output, for a state exercising every sub-block at once."""
    dummy_encounter = DEFAULT_ENCOUNTERS[0]
    env = STS2FullCombatEnv(
        encounter=dummy_encounter,
        deck=["strike", "defend", "bash", "whirlwind", "pommel_strike"],
        potions=["block_potion", "fire_potion"],
    )
    env.reset(seed=0)
    obs1 = build_combat_obs(env._state)
    obs2 = build_combat_obs(env._state)
    np.testing.assert_array_equal(obs1["f"], obs2["f"])
    np.testing.assert_array_equal(obs1["i"], obs2["i"])
    # And a fresh ObsBuffer-backed build after driving the state forward one
    # step must still land exactly on what env._build_obs() (the SAME code
    # path STS2FullCombatEnv.step returns) produces — build_combat_obs has no
    # env-only special case.
    env.step(0)
    np.testing.assert_array_equal(build_combat_obs(env._state)["f"], env._build_obs()["f"])
    np.testing.assert_array_equal(build_combat_obs(env._state)["i"], env._build_obs()["i"])


# ═════════════════════════════════════════════════════════════════════════
# 2. STS2RunEnv: the persistent-buffer hazard
# ═════════════════════════════════════════════════════════════════════════


def test_run_env_step_returns_independent_copy_despite_the_persistent_buffer():
    """STS2RunEnv reuses ONE ObsBuffer for the whole episode (unlike the
    combat env, which allocates fresh). That makes aliasing a live risk in a
    way it structurally isn't for the combat env: if ``_build_obs`` ever
    returned ``buf.as_obs()`` directly instead of copying, every previously
    returned observation in a rollout buffer would retroactively mutate on
    the next step()."""
    env = STS2RunEnv()
    obs1, _ = env.reset(seed=100)
    f1_snapshot, i1_snapshot = obs1["f"].copy(), obs1["i"].copy()
    mask = env.action_masks()
    obs2, *_ = env.step(int(np.flatnonzero(mask)[0]))
    obs2["f"][:] = -1.0
    obs2["i"][:] = 999_999
    np.testing.assert_array_equal(obs1["f"], f1_snapshot)
    np.testing.assert_array_equal(obs1["i"], i1_snapshot)
    assert not np.shares_memory(obs1["f"], obs2["f"])
    assert not np.shares_memory(obs1["i"], obs2["i"])


# Which DecisionKind(s) may legitimately leave a given phase-specific block
# non-PAD/non-zero. Built from run_env.py's actual write conditions (not just
# OBS_SCHEMA.md's table, which groups SELECT_CARDS/SELECT_OPTION together —
# the real code only ever populates select.candidates.* for SELECT_CARDS;
# SELECT_OPTION shares only the purpose/count/skippable trio).
_SELECT_SHARED = frozenset({DecisionKind.SELECT_CARDS, DecisionKind.SELECT_OPTION})

_PHASE_BLOCK_OWNERS: dict[str, frozenset] = {}
for _m in range(MAP_SLOTS):
    _PHASE_BLOCK_OWNERS[f"map{_m}"] = frozenset({DecisionKind.MAP})
for _name in ("event.present", "event.page", "event.options", "event.ids"):
    _PHASE_BLOCK_OWNERS[_name] = frozenset({DecisionKind.EVENT})
for _name in ("shop.cards.f", "shop.relics.f", "shop.potions.f", "shop.removal",
              "shop.cards.ids", "shop.relics.ids", "shop.potions.ids"):
    _PHASE_BLOCK_OWNERS[_name] = frozenset({DecisionKind.SHOP})
for _name in ("reward.cards.f", "reward.cards.ids"):
    _PHASE_BLOCK_OWNERS[_name] = frozenset({DecisionKind.REWARD_CARD})
for _name in ("reward.potion.f", "reward.potion.ids"):
    _PHASE_BLOCK_OWNERS[_name] = frozenset({DecisionKind.REWARD_POTION})
for _name in ("select.purpose.ids", "select.count", "select.skippable"):
    _PHASE_BLOCK_OWNERS[_name] = _SELECT_SHARED
for _name in ("select.candidates.f", "select.candidates.ids"):
    _PHASE_BLOCK_OWNERS[_name] = frozenset({DecisionKind.SELECT_CARDS})


def test_run_env_phase_blocks_do_not_leak_stale_data_across_a_phase_switch():
    """Walk masked-random run episodes and, at EVERY step, assert every
    phase-specific block owned by a DIFFERENT DecisionKind than the one
    currently pending reads fully PAD (int half) / zero (float half) —
    including the step immediately after a phase transition, which is
    exactly when a `reset()` that missed a segment or a write path that
    skipped clearing a tail would show up. Nothing in test_run_obs_v4.py
    drives an actual multi-phase episode this way (its tests build one
    request via surgery and call _build_obs() once), so this is the one test
    in the suite that would catch a leak that only appears ACROSS a
    transition rather than within a single hand-built state."""
    layout = run_obs_layout()
    env = STS2RunEnv()
    policy = masked_random_run_policy(random.Random(0))
    seen_owned_kinds: set = set()

    for seed in range(100, 140):
        obs, _ = env.reset(seed=seed)
        for _ in range(600):
            kind = env._request.kind if env._request is not None else None
            if kind in {DecisionKind.MAP, DecisionKind.EVENT, DecisionKind.SHOP,
                        DecisionKind.REWARD_CARD, DecisionKind.REWARD_POTION,
                        DecisionKind.SELECT_CARDS, DecisionKind.SELECT_OPTION}:
                seen_owned_kinds.add(kind)
            for name, owners in _PHASE_BLOCK_OWNERS.items():
                if kind in owners:
                    continue
                if name in layout.f_slices:
                    sl = layout.f_slices[name]
                    assert not np.any(obs["f"][sl]), (seed, kind, name)
                else:
                    sl = layout.i_slices[name]
                    assert not np.any(obs["i"][sl]), (seed, kind, name)
            mask = env.action_masks()
            action = policy(env, obs, mask)
            obs, reward, term, trunc, info = env.step(action)
            if term or trunc:
                break
        if len(seen_owned_kinds) >= 3:
            break

    assert len(seen_owned_kinds) >= 2, (
        f"fixture regression: only exercised {seen_owned_kinds} — need at "
        "least two distinct phase-specific blocks actually populated for "
        "the cross-phase zero check above to mean anything"
    )


# ═════════════════════════════════════════════════════════════════════════
# Retired (see report for the full accounting)
# ═════════════════════════════════════════════════════════════════════════
#
# - The entire `_ref_*` frozen-reference block (combat AND run-env) is
#   DELETED. It hard-codes the v3 dense/flat representation field-by-field
#   (one-hot hand/enemy identity, `power_triples`, `pile_composition`,
#   `ENEMY_ROW_DIM`-shaped rows, a flat run-obs concatenation) — none of
#   which corresponds to anything the v4/v7 builders produce. There is no
#   "same property, new address" rewrite available here: the thing it
#   checked (byte-for-byte agreement with THAT SPECIFIC OLD SHAPE) doesn't
#   apply to a schema where the shape itself changed on purpose. Content
#   correctness for the new schema is covered by test_combat_obs_v4.py and
#   test_run_obs_v4.py (built TDD-first against OBS_SCHEMA.md, per their own
#   docstrings) — re-deriving a second, hand-rolled oracle here would be the
#   "two divergent versions" trap the project brief warns against.
#
# - test_rich_combat_matches_reference / test_combat_episodes_match_reference
#   / test_run_env_matches_reference_all_phases /
#   test_curriculum_run_env_matches_reference: DELETED along with the
#   reference they compared against, for the same reason. The part of their
#   value that survives independently of the reference — driving many
#   seeds/steps without crashing or leaving the declared bounds — is already
#   covered by test_full_env.py::test_every_encounter_runs_to_completion
#   (masked-random rollout to completion, asserting observation_space.
#   contains(obs) every step) and test_run_obs_v4.py's own coverage sweep
#   (test_run_env_matches_reference_all_phases in THAT file, which requires
#   MAP/EVENT/COMBAT/REWARD_CARD/SELECT_CARDS/REST to all be visited).
#   test_curriculum_run_env_matches_reference specifically: STS2CurriculumRunEnv
#   does not override `_build_obs`, `reset`, or `step` (verified by reading
#   curriculum_env.py) — it inherits STS2RunEnv's exact buffer-reuse code
#   path, so the two new STS2RunEnv tests above already exercise curriculum
#   runs' only distinct machinery (RunState subclassing) indirectly through
#   the same method; a third copy of the buffer-safety tests parametrized
#   over the curriculum env would test the RunState swap, not the
#   observation builder, which is out of this file's scope.
#
# - test_step_returns_independent_copy (STS2FullCombatEnv only, "f" half
#   only): SUPERSEDED by test_full_env_step_returns_independent_copy above,
#   which checks both halves.
#
# - test_public_sub_builders_still_return_lists: DELETED. It pinned that
#   `full_env.power_triples`/`full_env.pile_composition` still existed as a
#   public list-returning API alongside the vectorized in-place builder. Both
#   functions are gone, not renamed — v4 represents powers/piles as sparse
#   id/float ROWS (`_power_rows`/`_cards_rows`, module-private, feeding
#   `ObsBuffer.write_rows`), not a dense list over the full vocabulary, so
#   there is no "list-returning sub-builder" API left for this property to be
#   about. The underlying content (a power's encoded triple, a pile's
#   composition) is pinned in its new sparse-row form by
#   test_combat_obs_v4.py (e.g. test_the_bomb_two_instances_are_two_rows_
#   with_distinct_aux, test_cards_block_is_exact_multiset_of_the_three_piles)
#   and by test_full_env.py::test_full_power_vocabulary_and_power_row_encoding.
