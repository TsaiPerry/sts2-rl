"""Buffer-safety tests for the v4/v7 observation builders (OBS_SCHEMA.md).

Pins two reused-buffer/aliasing hazards:
1. ``STS2FullCombatEnv``/``build_combat_obs`` allocate a fresh ``ObsBuffer``
   per call but promise callers independent copies — a caller mutating one
   returned observation must never affect a previously returned one.
2. ``STS2RunEnv`` keeps ONE ``ObsBuffer`` for the WHOLE episode, rewritten
   every step; a block not live this step must be PAD/zero, never stale
   content from a previous step. test_run_obs_v4.py is unit-style (builds
   one request via surgery, calls _build_obs() once), so it can't catch a
   leak that only appears ACROSS a phase transition — this file does.

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
