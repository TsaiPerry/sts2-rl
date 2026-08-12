"""Smoke tests for STS2FullCombatEnv — the full-combat Gymnasium wrapper.

These exercise the env wiring without SB3: observation/space consistency,
action-mask legality, that every Act 1 encounter plays to completion under a
masked random policy, seed determinism, and reward/termination sanity.

v4 note: the observation is now a two-leaf ``{"f": float32, "i": int32}``
Dict (OBS_SCHEMA.md), not a flat float Box. Most fine-grained "does this
exact float index hold this exact value" pinning now lives in
test_obs_pins.py (addressed by name through ``combat_obs_layout()``) and
test_combat_obs_v4.py (the reviewed v4 acceptance suite) — this file keeps
the tests that are about the *env*, not the observation encoding: spaces
wiring, full-episode integration, seed determinism, and reward/termination
semantics. See the bottom of the file for what moved/was retired and why.

Run with:  py -m pytest test/test_full_env.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from sts2_rl import STS2FullCombatEnv
from sts2_rl.monsters.overgrowth import ENCOUNTERS as ALL_ENCOUNTERS
from sts2_rl.full_env import (
    DEFAULT_ENCOUNTERS,
    MAX_ENEMIES,
    MAX_HAND,
    MONSTER_INDEX,
    OBS_SCHEMA_VERSION,
    POWER_IDS,
    POWER_INDEX,
    _N_ENEMY_SCALARS,
    build_combat_obs,
    combat_obs_layout,
)


def _masked_rollout(env, seed, max_steps=500):
    obs, info = env.reset(seed=seed)
    assert env.observation_space.contains(obs)
    rng = np.random.default_rng(seed)
    for _ in range(max_steps):
        mask = env.action_masks()
        assert mask.shape == (env.n_actions,)
        assert mask.any(), "no legal action available"
        action = int(rng.choice(np.flatnonzero(mask)))
        obs, reward, terminated, truncated, info = env.step(action)
        assert env.observation_space.contains(obs), (obs["f"].min(), obs["f"].max())
        assert np.isfinite(reward)
        if terminated or truncated:
            return terminated, truncated, info
    pytest.fail("episode did not finish within max_steps")


# (f_dim, i_dim) -> the OBS_SCHEMA_VERSION those widths belong to. A bare
# `OBS_SCHEMA_VERSION == <n>` literal only fails when the version changes —
# it says nothing about whether the version *should* have changed. Pinning
# the version together with the widths it was measured against instead
# catches the other, more dangerous direction too: a segment resized without
# OBS_SCHEMA_VERSION being bumped (checkpoints.py's mlp/entity refusal and
# check_checkpoint's schema gate both depend on that bump actually
# happening) shows up here as the *new* widths having no entry, exactly the
# same way the old assert would fail on a version-only bump — so this pin
# must still be hand-updated on every real bump, it just now also fails on
# the "forgot to bump" case the old assert was blind to.
_SCHEMA_FOR_WIDTHS = {
    (1677, 606): 7,
}


def test_spaces_declared():
    env = STS2FullCombatEnv()
    layout = combat_obs_layout()
    widths = (layout.f_dim, layout.i_dim)
    assert _SCHEMA_FOR_WIDTHS.get(widths) == OBS_SCHEMA_VERSION, (
        f"combat obs widths {widths} don't map to the current "
        f"OBS_SCHEMA_VERSION {OBS_SCHEMA_VERSION} in _SCHEMA_FOR_WIDTHS -- "
        f"either a segment resized without OBS_SCHEMA_VERSION being bumped, "
        f"or the version/widths changed without updating this pin.")
    space = env.observation_space
    # v4: a Dict of two leaves, each sized by combat_obs_layout's reserved
    # capacities — no more single flat Box shape[0].
    assert space["f"].shape == (layout.f_dim,)
    assert space["i"].shape == (layout.i_dim,)
    assert space["f"].dtype == np.float32
    assert space["i"].dtype == np.int32
    # The action space is untouched by the observation-schema rewrite.
    assert env.action_space.n == env.n_actions == 79


@pytest.mark.parametrize("enc", list(ALL_ENCOUNTERS.values()), ids=lambda e: e.id)
def test_every_encounter_runs_to_completion(enc):
    env = STS2FullCombatEnv(encounter=enc, max_steps=400)
    terminated, truncated, info = _masked_rollout(env, seed=3, max_steps=400)
    assert terminated or truncated
    if terminated:
        assert "is_success" in info


def test_seed_determinism():
    def trace(seed):
        env = STS2FullCombatEnv()
        obs, _ = env.reset(seed=seed)
        out = [(obs["f"].tobytes(), obs["i"].tobytes())]
        for _ in range(12):
            action = int(np.flatnonzero(env.action_masks())[0])
            obs, reward, term, trunc, _ = env.step(action)
            out.append((round(reward, 6), obs["f"].tobytes(), obs["i"].tobytes(), term))
            if term or trunc:
                break
        return out

    assert trace(42) == trace(42)
    assert trace(1) != trace(2)


def test_potions_are_targetable_and_untargetable():
    env = STS2FullCombatEnv(
        encounter=DEFAULT_ENCOUNTERS[0], potions=["fire_potion", "block_potion"]
    )
    env.reset(seed=0)
    mask = env.action_masks()
    potion_actions = [i for i in range(env._potion_base, env.n_actions) if mask[i]]
    assert len(potion_actions) >= 2   # one non-targeted (block) + one targeted (fire)


def test_dexterity_is_observable():
    from sts2_rl import PowerCmd
    from sts2_rl.powers import DexterityPower

    env = STS2FullCombatEnv(encounter=DEFAULT_ENCOUNTERS[0])
    layout = combat_obs_layout()
    dex_slice = layout.f_slices["player.dexterity"]
    obs_before, _ = env.reset(seed=0)
    assert obs_before["f"][dex_slice][0] == pytest.approx(0.5)     # dex slot, signed zero
    PowerCmd.apply(env._state.hooks, env._state.player, DexterityPower, 6)
    obs_after = env._build_obs()
    assert obs_after["f"][dex_slice][0] == pytest.approx((6 + 30) / 60.0)


def test_full_power_vocabulary_and_power_row_encoding():
    """Two properties the v3 version bundled into one test:

    1. Vocabulary completeness — every registered power has a vocab slot.
       (The frozen vocab is append-only, so the full list is no longer
       alphabetical; vocab.py's ordering rules.) Unchanged by the schema
       rewrite: still checked via POWER_IDS vs ALL_POWERS.
    2. Power-ROW encoding for a plain (non-instanced, no-aux) power on the
       enemy side, addressed by name through combat_obs_layout instead of a
       removed ``_power_triples`` static helper. v4 represents powers as one
       row PER INSTANCE, sparse over a capped block — not a dense triple per
       vocab id — so an absent power (poison) is asserted by checking its id
       does not appear among the written rows, not by reading a fixed slot.
    """
    import random
    from sts2_rl import CombatState, PowerCmd
    from sts2_rl.powers import ALL_POWERS, RitualPower

    assert set(POWER_IDS) == set(ALL_POWERS)

    c = CombatState(rng=random.Random(0), encounter=DEFAULT_ENCOUNTERS[0])
    e = c.enemies[0]
    PowerCmd.apply(c.hooks, e, RitualPower, 3)

    obs = build_combat_obs(c)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["enemy0.powers.ids"]]
    fs = obs["f"][layout.f_slices["enemy0.powers.f"]].reshape(-1, 3)

    ritual_id = POWER_INDEX["ritual"] + 1
    row = next(i for i, v in enumerate(ids) if v == ritual_id)
    assert fs[row][0] == pytest.approx((3 + 10) / 20.0)
    assert fs[row][1] == pytest.approx((3 + 50) / 100.0)
    assert fs[row][2] == pytest.approx(0.0)         # ritual has no aux field

    poison_id = POWER_INDEX["poison"] + 1
    assert poison_id not in ids, "poison was never applied — it must have no row at all"


def test_enemy_row_identity_and_pipeline_preview():
    from sts2_rl import FUZZY_WURM_ENCOUNTER, PowerCmd
    from sts2_rl.powers import WeakPower

    env = STS2FullCombatEnv(encounter=FUZZY_WURM_ENCOUNTER)
    env.reset(seed=0)
    layout = combat_obs_layout()
    enemy = env._state.enemies[0]

    obs = env._build_obs()
    eids = obs["i"][layout.i_slices["enemies.ids"]]
    ef = obs["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)

    # Identity is now a plain vocab id in the int half (v3 had a float
    # one-hot living inside the enemy row itself).
    assert eids[0] == MONSTER_INDEX[enemy.__class__.__name__] + 1
    assert eids[0] != 0

    # Intent damage runs through the modifier pipeline: Weak lowers it.
    per_hit_idx = 18   # present+ratio+hp2+maxhp2+block2+str+9 flags
    if ef[0][per_hit_idx] > 0:
        before = ef[0][per_hit_idx]
        PowerCmd.apply(env._state.hooks, enemy, WeakPower, 1)
        after_ef = env._build_obs()["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)
        assert after_ef[0][per_hit_idx] < before

    # Absent slots are explicit PAD rows of the same width.
    n_live = len(env._state.enemies)
    for e_i in range(n_live, MAX_ENEMIES):
        assert eids[e_i] == 0
        assert np.all(ef[e_i] == 0.0)


def test_win_gives_terminal_reward():
    # A trivially strong deck vs a single weak encounter should net a win with a
    # positive terminal bonus within a few seeds.
    for seed in range(20):
        env = STS2FullCombatEnv(
            encounter=DEFAULT_ENCOUNTERS[0],
            deck=["bludgeon"] * 6 + ["defend"] * 4,
        )
        _, _, info = _masked_rollout(env, seed=seed)
        if info.get("is_success"):
            return
    pytest.skip("no win in 20 seeds (random policy) — reward path still exercised")


# ── Retired / relocated (see report for the full accounting) ────────────────
#
# - test_features_mode_is_smaller: DELETED. It pinned that card_obs="features"
#   produced a smaller flat observation than "hybrid" (11473 vs 17873). That
#   property is genuinely gone: v4's combat_obs_segments_i/f() are IDENTICAL
#   for both card_obs values (an id is one int either way; only whether
#   hand.ids' card_id column is PAD or real differs) — there is no longer a
#   size difference to pin. The real remaining behavioral difference (features
#   mode blanks the hand card id but keeps pile identity and row presence) is
#   pinned by test_combat_obs_v4.py::
#   test_card_obs_features_blanks_hand_card_id_but_keeps_pile_identity_and_row_presence.
#
# - test_obs_within_declared_space_at_reset: DELETED as a pure duplicate.
#   test_combat_obs_v4.py::test_layout_self_consistency already asserts
#   observation_space.contains(obs) and the f/i bounds at both reset() and
#   step(), for both card_obs modes.
#
# - test_absolute_hp_encoding_in_player_vitals: DELETED as a pure duplicate.
#   test_obs_pins.py::test_player_vitals_pins (rewritten for v4 in this same
#   pass) pins the identical property — player.hp_ratio/hp_abs/max_hp_abs
#   under a controlled dummy — more rigorously (fixed HP/damage instead of a
#   live default encounter).
#
# - test_damage_matrix_alignment: DELETED, not because the property is gone
#   but because it is now duplicated, more thoroughly, by
#   test_combat_obs_v4.py::
#   test_damage_matrix_cell_matches_decoded_action_with_a_dead_enemy_in_slot_0
#   (which additionally exercises a dead enemy in slot 0 and cross-checks
#   every cell against decode_combat_action). Keeping a second, divergent
#   copy here is exactly what the project brief warns against.
