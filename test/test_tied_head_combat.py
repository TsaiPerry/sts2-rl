"""Tests for the combat env's tied action head (`sts2_rl/models.py`'s
`ActionLayout` + `EntitySetActorCritic` head assembly -- T7 brief §3/§4,
phase-2 Tasks 3-4).

These build agents directly (real f/i segment args from
``checkpoints.model_obs_layout``, mirroring how `test/test_models.py` and
`test/test_entset_rows.py` already construct `EntitySetActorCritic`) AND via
`checkpoints.make_model` for `env_kind="combat"`, so both the low-level
constructor contract and the production wiring path are covered.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
import torch

from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.full_env import (
    DEFAULT_ENCOUNTERS,
    MAX_ENEMIES,
    MAX_HAND,
    MAX_POTIONS,
    STS2FullCombatEnv,
    combat_action_count,
    combat_obs_layout,
)
from sts2_rl.models import EntitySetActorCritic, _MASK_FILL, combat_action_layout
from sts2_rl.tensor_obs import TensorObs

COMBAT_N_ACTIONS = combat_action_count(MAX_POTIONS)   # 79
PLAY_BASE = 1
POTION_BASE = PLAY_BASE + MAX_HAND * MAX_ENEMIES       # 61


def _build_model(hidden=(32,)) -> tuple[EntitySetActorCritic, object]:
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    layout = combat_action_layout(MAX_POTIONS)
    model = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, layout, hidden=hidden)
    return model, layout


def _reset_env(seed: int = 0, **kw):
    env = STS2FullCombatEnv(**kw)
    obs, _info = env.reset(seed=seed)
    return env, obs


def _to_tobs(obs: dict) -> TensorObs:
    return TensorObs.from_dict(obs, device="cpu")[None]


def _copy_obs(obs: dict) -> dict:
    return {"f": np.array(obs["f"], copy=True), "i": np.array(obs["i"], copy=True)}


def _swap_row(half: np.ndarray, sl: slice, cap: int, r1: int, r2: int) -> None:
    """Swap rows ``r1``/``r2`` within one ``(cap, stride)`` block of a flat
    obs half, in place."""
    width = sl.stop - sl.start
    stride = width // cap
    view = half[sl].reshape(cap, stride)
    view[[r1, r2]] = view[[r2, r1]]


def _swap_segment(half: np.ndarray, sl1: slice, sl2: slice) -> None:
    """Swap two whole same-width segments (e.g. `enemy0.powers.*` <->
    `enemy1.powers.*`), in place."""
    assert (sl1.stop - sl1.start) == (sl2.stop - sl2.start)
    tmp = half[sl1].copy()
    half[sl1] = half[sl2]
    half[sl2] = tmp


def _all_legal_mask(n: int) -> torch.Tensor:
    return torch.ones(1, n, dtype=torch.bool)


# ── 1. layout tiling ─────────────────────────────────────────────────────


def test_layout_tiles_action_space():
    layout = combat_action_layout(MAX_POTIONS)
    assert layout.n_actions == COMBAT_N_ACTIONS == 79
    _src, _tgt, S, T = layout.play
    assert S * T == 60
    _src, _tgt, S_used, T = layout.potion_pairs
    assert S_used * T == 18
    assert 1 + 60 + 18 == 79

    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    # A deliberately corrupted layout: a positional range whose base
    # OVERLAPS the potion-pair range's end (79) instead of starting there.
    bad = replace(layout, n_actions=80, positional=((78, 1),))
    with pytest.raises(ValueError):
        EntitySetActorCritic(f_segments, i_segments, 80, bad, hidden=(32,))

    # Also: make_model builds the same tiling for env_kind="combat".
    obs_dim = (sum(w for _, w in f_segments), sum(w for _, w in i_segments))
    built = make_model(ModelSpec("combat", arch="entset", hidden=(32,)), obs_dim, COMBAT_N_ACTIONS)
    assert built.action_layout.n_actions == COMBAT_N_ACTIONS
    assert built.n_actions == COMBAT_N_ACTIONS


# ── 2. contract shapes ───────────────────────────────────────────────────


def test_contract_shapes():
    model, _layout = _build_model()

    # Mutation check (b), brief §"mutation checks": the play and potion
    # blocks are different decision kinds and must be scored by SEPARATE
    # PairPointerHead instances with their own weights, not one head
    # instance reused for both (a shared-weights bug the equivariance tests
    # above cannot see, since neither play nor potion output is compared
    # against the other's -- confirmed empirically in the report). Pinned
    # here directly rather than relying on those tests to notice.
    assert model.play_head is not model.potion_head
    play_params = list(model.play_head.parameters())
    potion_params = list(model.potion_head.parameters())
    assert not all(torch.equal(a, b) for a, b in zip(play_params, potion_params)), (
        "play_head and potion_head must be independently-initialized "
        "instances -- identical parameters would mean they're aliased "
        "(shared weights) rather than separately owned.")

    env, obs = _reset_env(seed=0)
    mask_np = env.action_masks()
    tobs = _to_tobs(obs)
    mask = torch.as_tensor(mask_np, dtype=torch.bool).unsqueeze(0)

    value = model.get_value(tobs)
    assert value.shape == (1,)

    action, logp, entropy, value2 = model.get_action_and_value(tobs, mask)
    assert action.shape == (1,)
    assert logp.shape == (1,)
    assert entropy.shape == (1,)
    assert value2.shape == (1,)
    assert mask_np[int(action.item())], "a sampled action must always be legal"

    illegal = (~mask[0]).nonzero(as_tuple=True)[0]
    assert illegal.numel() > 0, "fixture sanity: at least one illegal action expected"
    logits = model.action_logits(tobs, mask)
    assert torch.all(logits[0, illegal] == _MASK_FILL)


# ── 3. hand-swap equivariance (play block) ───────────────────────────────


def _distinct_hand_pair(obs: dict) -> tuple[int, int]:
    layout_obs = combat_obs_layout()
    hand_ids = np.asarray(obs["i"])[layout_obs.i_slices["hand.ids"]].reshape(MAX_HAND, 3)[:, 0]
    for a in range(MAX_HAND):
        for b in range(a + 1, MAX_HAND):
            if hand_ids[a] != 0 and hand_ids[b] != 0 and hand_ids[a] != hand_ids[b]:
                return a, b
    raise AssertionError("fixture sanity: need two hand slots with different card ids")


def test_hand_swap_equivariance():
    model, _layout = _build_model()
    env, obs = _reset_env(seed=0)
    h1, h2 = _distinct_hand_pair(obs)

    layout_obs = combat_obs_layout()
    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], layout_obs.i_slices["hand.ids"], MAX_HAND, h1, h2)
    _swap_row(obs_b["f"], layout_obs.f_slices["hand.f"], MAX_HAND, h1, h2)
    # R9: damage_matrix is now also a play-head PAIR feature, keyed on the
    # hand axis (row h = hand slot h's per-enemy damage row) -- a hand-only
    # swap must swap its two rows too, or the pair tensor stops being
    # equivariant under the swap (caught this: without this line the test
    # went red with a real, if small, numeric mismatch, not a crash -- the
    # two hand cards' damage rows legitimately differ).
    _swap_row(obs_b["f"], layout_obs.f_slices["damage_matrix"], MAX_HAND, h1, h2)

    mask_all = _all_legal_mask(COMBAT_N_ACTIONS)
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask_all)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask_all)[0]

    # R9 report finding (brief premise correction): `damage_matrix` was
    # ALREADY a raw pooled feature feeding `ctx` directly (T7/R8, unrelated
    # to R9) -- `_EntsetEncoder.encode`'s raw-segment concatenation, not
    # anything this task added. Swapping its two rows (needed above for the
    # pair path's own equivariance) therefore also perturbs `ctx` by a tiny
    # amount, which every logit -- including ones the swap "shouldn't touch"
    # -- inherits uniformly (measured ~7e-5 max in this fixture; see
    # report). `atol=1e-5` (this file's usual bound for a pooled-sum's
    # exact permutation invariance) is too tight for that residual; 5e-4
    # comfortably clears the measured noise floor while still being tight
    # enough that a real equivariance bug (which moves logits by orders of
    # magnitude more, per the mutation-check evidence in the report) would
    # still be caught.
    atol = 5e-4
    for e in range(MAX_ENEMIES):
        idx_h1 = PLAY_BASE + h1 * MAX_ENEMIES + e
        idx_h2 = PLAY_BASE + h2 * MAX_ENEMIES + e
        assert torch.allclose(logits_b[idx_h1], logits_a[idx_h2], atol=atol)
        assert torch.allclose(logits_b[idx_h2], logits_a[idx_h1], atol=atol)

    for h in range(MAX_HAND):
        if h in (h1, h2):
            continue
        for e in range(MAX_ENEMIES):
            idx = PLAY_BASE + h * MAX_ENEMIES + e
            assert torch.allclose(logits_b[idx], logits_a[idx], atol=atol)

    # end-turn + every potion logit: untouched BY THE PLAY-EQUIVARIANCE
    # PROPERTY (they don't permute) -- but not bit-identical, per the
    # ctx-coupling note above.
    assert torch.allclose(logits_b[0], logits_a[0], atol=atol)
    assert torch.allclose(logits_b[POTION_BASE:], logits_a[POTION_BASE:], atol=atol)


# ── 4. enemy-swap equivariance (play + potion blocks, target axis) ───────


def _multi_enemy_encounter():
    for enc in DEFAULT_ENCOUNTERS:
        if len(enc.monster_classes) >= 2:
            return enc
    raise AssertionError("fixture sanity: need an encounter with >=2 monster classes")


def test_enemy_swap_equivariance():
    model, _layout = _build_model()
    encounter = _multi_enemy_encounter()
    env, obs = _reset_env(seed=0, encounter=encounter)

    layout_obs = combat_obs_layout()
    enemy_ids = np.asarray(obs["i"])[layout_obs.i_slices["enemies.ids"]]
    living = [i for i in range(MAX_ENEMIES) if enemy_ids[i] != 0]
    assert len(living) >= 2, "fixture sanity: need >=2 living enemies"
    e1, e2 = living[0], living[1]

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], layout_obs.i_slices["enemies.ids"], MAX_ENEMIES, e1, e2)
    _swap_row(obs_b["f"], layout_obs.f_slices["enemies.f"], MAX_ENEMIES, e1, e2)
    _swap_segment(obs_b["i"], layout_obs.i_slices[f"enemy{e1}.powers.ids"],
                  layout_obs.i_slices[f"enemy{e2}.powers.ids"])
    _swap_segment(obs_b["f"], layout_obs.f_slices[f"enemy{e1}.powers.f"],
                  layout_obs.f_slices[f"enemy{e2}.powers.f"])
    _swap_segment(obs_b["f"], layout_obs.f_slices[f"enemy{e1}.powers.overflow"],
                  layout_obs.f_slices[f"enemy{e2}.powers.overflow"])
    _swap_segment(obs_b["f"], layout_obs.f_slices[f"enemy{e1}.intent_history.f"],
                  layout_obs.f_slices[f"enemy{e2}.intent_history.f"])
    dm_sl = layout_obs.f_slices["damage_matrix"]
    dm = obs_b["f"][dm_sl].reshape(MAX_HAND, MAX_ENEMIES)
    dm[:, [e1, e2]] = dm[:, [e2, e1]]

    mask_all = _all_legal_mask(COMBAT_N_ACTIONS)
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask_all)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask_all)[0]

    def _src(e: int) -> int:
        return e2 if e == e1 else e1 if e == e2 else e

    for h in range(MAX_HAND):
        for e in range(MAX_ENEMIES):
            idx_b = PLAY_BASE + h * MAX_ENEMIES + e
            idx_a = PLAY_BASE + h * MAX_ENEMIES + _src(e)
            assert torch.allclose(logits_b[idx_b], logits_a[idx_a], atol=1e-5)

    for p in range(MAX_POTIONS):
        for e in range(MAX_ENEMIES):
            idx_b = POTION_BASE + p * MAX_ENEMIES + e
            idx_a = POTION_BASE + p * MAX_ENEMIES + _src(e)
            assert torch.allclose(logits_b[idx_b], logits_a[idx_a], atol=1e-5)

    assert torch.allclose(logits_b[0], logits_a[0], atol=1e-5)


# ── 5. sanity: a positional (ctx-only) baseline does NOT have this property


def test_positional_baseline_fails_equivariance():
    model, _layout = _build_model()
    env, obs = _reset_env(seed=0)
    h1, h2 = _distinct_hand_pair(obs)

    layout_obs = combat_obs_layout()
    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], layout_obs.i_slices["hand.ids"], MAX_HAND, h1, h2)
    _swap_row(obs_b["f"], layout_obs.f_slices["hand.f"], MAX_HAND, h1, h2)

    with torch.no_grad():
        pooled_a = model.actor_encoder(_to_tobs(obs))
        pooled_b = model.actor_encoder(_to_tobs(obs_b))

    torch.manual_seed(0)
    baseline = torch.nn.Linear(pooled_a.shape[-1], COMBAT_N_ACTIONS)
    with torch.no_grad():
        out_a = baseline(pooled_a)[0]
        out_b = baseline(pooled_b)[0]

    idx_h1_e0 = PLAY_BASE + h1 * MAX_ENEMIES + 0
    idx_h2_e0 = PLAY_BASE + h2 * MAX_ENEMIES + 0
    equivariant = torch.allclose(out_b[idx_h1_e0], out_a[idx_h2_e0], atol=1e-5)
    assert not equivariant, (
        "sanity check is broken: a plain ctx-only Linear head unexpectedly "
        "satisfied the equivariance property -- the hand-swap tests above "
        "would then be unable to distinguish a real pointer head from this "
        "baseline")


# ── 6b. batched actor path has no cross-example crosstalk ────────────────


def test_action_logits_batched_no_crosstalk():
    """Stack two DIFFERENT combat observations (different seeds) into a
    batch of 2 and check each row of the batched ``action_logits`` output
    equals what a lone, un-batched call to that same observation produces.

    Closes a review finding: the per-module batch test in
    ``test_action_heads.py`` exercises ``PairPointerHead`` in isolation, but
    nothing previously proved the ASSEMBLED head path
    (``EntitySetActorCritic.action_logits``, wiring ``play_head`` /
    ``potion_head`` / ``end_turn_head`` / ``positional_heads`` together over
    a real encoder) keeps batch elements independent end to end -- a
    concatenation or broadcast bug anywhere in that assembly could leak
    batch index 0's features into batch index 1's logits (or vice versa)
    without any single-example test ever seeing it.
    """
    model, _layout = _build_model()
    env0, obs0 = _reset_env(seed=0)
    env1, obs1 = _reset_env(seed=1)

    tobs0 = _to_tobs(obs0)      # already batch-of-1, via TensorObs[None]
    tobs1 = _to_tobs(obs1)
    batched = TensorObs(
        torch.cat([tobs0.f, tobs1.f], dim=0),
        torch.cat([tobs0.i, tobs1.i], dim=0),
    )

    mask0 = torch.as_tensor(env0.action_masks(), dtype=torch.bool).unsqueeze(0)
    mask1 = torch.as_tensor(env1.action_masks(), dtype=torch.bool).unsqueeze(0)
    mask_batch = torch.cat([mask0, mask1], dim=0)

    with torch.no_grad():
        logits_single_0 = model.action_logits(tobs0, mask0)[0]
        logits_single_1 = model.action_logits(tobs1, mask1)[0]
        logits_batched = model.action_logits(batched, mask_batch)

    assert logits_batched.shape == (2, COMBAT_N_ACTIONS)
    assert torch.allclose(logits_batched[0], logits_single_0, atol=1e-6)
    assert torch.allclose(logits_batched[1], logits_single_1, atol=1e-6)


# ── 6. PAD hand slot inertness — SKIPPED, see report ─────────────────────
#
# Brief §6 explicitly allows skipping this one if fiddly and says so in the
# report rather than silently dropping it: fabricating a second, VALID
# alternate card id + its full 29-float feature row for "another slot" (so
# the PAD slot's row genuinely stays the zero vector while only "another
# slot" changes) requires synthesizing a legitimate feature encoding, not
# just flipping a scalar -- the risk of the fabricated row itself being
# malformed (and the test therefore not testing what it claims) outweighs
# the marginal coverage over what test_pad_rows_are_zero_vectors
# (test/test_entset_rows.py) and the hand-swap test above already pin.


# ── 10. R9: pair features in the tied combat head ────────────────────────
#
# `damage_matrix` and (per-enemy) `enemies.f[18:24]` were ALREADY raw
# pooled features feeding `ctx` directly (T7/R8's `_EntsetEncoder.encode`
# concatenates every unconsumed `.f` segment straight into `pooled`, and
# `enemies.f` is also the `enemies` row block's float sibling) -- this is
# NOT something R9 introduced. What R9 adds is a SECOND, more direct path:
# these same floats also feed the play `PairPointerHead` as an explicit
# per-(hand, enemy) `pair=` tensor. Both tests below therefore measure the
# extra PAIR-path contribution against the small residual ctx-mediated
# shift every logit already inherits from that pre-existing coupling,
# rather than asserting the ctx-mediated shift is exactly zero (the brief's
# literal "unchanged" phrasing for test 1 does not hold bit-exactly here --
# see the report; the ratio-based assertions below are what actually
# distinguishes "the pair path is live" from "nothing changed").


def test_damage_matrix_reaches_play_logits():
    """R9 brief test 1, with one deliberate operationalization change from
    the brief's literal wording (report finding): the brief says "zero the
    damage_matrix slice of obs.f", but `damage_matrix` was ALREADY a raw
    feature feeding `ctx` directly before R9 -- zeroing it in `obs.f` moves
    `ctx` too, so end-turn/potion logits do NOT come out bit-identical that
    way (measured ~1e-4, same order as the play block's own shift -- not a
    clean signal). What actually isolates the R9-specific pair PATH is
    zeroing the derived pair TENSOR itself (this test's monkeypatch) while
    leaving `obs.f` -- and therefore `ctx` -- completely untouched: with an
    identical `ctx`, end-turn/potion (which never read the pair tensor) are
    then bit-identical BY CONSTRUCTION, and any play-logit change is
    unambiguously the pair path's own contribution. This monkeypatch IS
    the brief's own suggested mutation check (a) ("monkeypatching the pair
    tensor to zeros inside the model") -- promoted here from a mutation
    check into the test's actual mechanism, since it is strictly the
    cleaner experiment."""
    model, _layout = _build_model()
    env, obs = _reset_env(seed=0)
    tobs = _to_tobs(obs)
    mask_all = _all_legal_mask(COMBAT_N_ACTIONS)

    real_play_pair_features = model.actor_encoder.play_pair_features

    def _zeroed_pair(obs_arg, dm_name, enemy_f_name, S, T):
        return torch.zeros_like(real_play_pair_features(obs_arg, dm_name, enemy_f_name, S, T))

    with torch.no_grad():
        logits_real = model.action_logits(tobs, mask_all)[0]
        model.actor_encoder.play_pair_features = _zeroed_pair
        try:
            logits_zeroed_pair = model.action_logits(tobs, mask_all)[0]
        finally:
            model.actor_encoder.play_pair_features = real_play_pair_features

    play_delta = (logits_real[PLAY_BASE:POTION_BASE]
                  - logits_zeroed_pair[PLAY_BASE:POTION_BASE]).abs()
    assert play_delta.max() > 2e-5, (
        "zeroing the pair tensor must move at least one play logit -- the "
        "pair path's liveness signal")

    # Same obs -> identical ctx -> end_turn_head/potion_head (which never
    # see the pair tensor) must be BIT-IDENTICAL, not merely close.
    assert torch.equal(logits_real[0], logits_zeroed_pair[0])
    assert torch.equal(logits_real[POTION_BASE:], logits_zeroed_pair[POTION_BASE:])


def test_enemy_preview_reaches_play_logits():
    """R9 brief test 2: perturbing one living enemy's `enemies.f[18:24]`
    incoming-attack preview must move that enemy's play-logit COLUMN by a
    genuinely different amount than the shared ctx-mediated shift every
    other column also gets (mutation check (b): a wrong-axis broadcast --
    e.g. broadcasting the preview across the ENEMY axis instead of the
    HAND axis -- would still move logits, but every column roughly
    equally, so it must fail the "differs from the others" assertion, not
    just the "is nonzero" one)."""
    model, _layout = _build_model()
    encounter = _multi_enemy_encounter()
    env, obs = _reset_env(seed=0, encounter=encounter)

    layout_obs = combat_obs_layout()
    enemy_ids = np.asarray(obs["i"])[layout_obs.i_slices["enemies.ids"]]
    living = [i for i in range(MAX_ENEMIES) if enemy_ids[i] != 0]
    assert len(living) >= 2, "fixture sanity: need >=2 living enemies"
    target = living[0]

    ef_sl = layout_obs.f_slices["enemies.f"]
    n_float = (ef_sl.stop - ef_sl.start) // MAX_ENEMIES
    assert n_float >= 24, "fixture sanity: enemies.f must carry fields 0-23"

    obs_b = _copy_obs(obs)
    view = obs_b["f"][ef_sl].reshape(MAX_ENEMIES, n_float)
    view[target, 18:24] += 0.3

    mask_all = _all_legal_mask(COMBAT_N_ACTIONS)
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask_all)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask_all)[0]

    col_deltas = []
    for e in range(MAX_ENEMIES):
        idxs = [PLAY_BASE + h * MAX_ENEMIES + e for h in range(MAX_HAND)]
        col_deltas.append((logits_b[idxs] - logits_a[idxs]).abs().max().item())

    target_delta = col_deltas[target]
    other_deltas = [d for e, d in enumerate(col_deltas) if e != target]

    assert target_delta > 1e-4, (
        "perturbing an enemy's preview must move its own play-logit column")
    assert not all(abs(target_delta - d) < 1e-6 for d in other_deltas), (
        "the targeted enemy's column shift must differ from a uniform "
        "ctx-mediated shift shared by every column -- a wrong-axis "
        "broadcast (enemy-axis instead of hand-axis) would move every "
        "column by roughly the SAME amount and slip past a plain "
        "'nonzero' check")


def test_enemy_preview_pair_feature_broadcasts_hand_axis_only():
    """Report finding: `test_enemy_preview_reaches_play_logits` above goes
    through the FULL model (`action_logits`), where `damage_matrix` and the
    `enemies` row block ALSO vary per enemy independently of the preview
    slice -- those other channels give every column some natural variation
    of their own, which weakens mutation check (b)'s "wrong axis" signal
    (verified empirically: a mutation that collapses the preview to the
    living enemies' MEAN before broadcasting -- exactly a "broadcast the
    wrong axis" bug's effect -- still slipped past that test's "columns
    differ" assertion, because the OTHER channels still varied per column;
    see the report). This test isolates `_EntsetEncoder.play_pair_features`
    directly, where the preview's specific 6 features are the ONLY
    thing that can vary, and pins its structure exactly: identical across
    the hand axis (broadcast), present only in the target enemy's column,
    and the damage_matrix feature (index 0) untouched by an
    `enemies.f`-only obs change."""
    model, _layout = _build_model()
    encounter = _multi_enemy_encounter()
    env, obs = _reset_env(seed=0, encounter=encounter)

    layout_obs = combat_obs_layout()
    enemy_ids = np.asarray(obs["i"])[layout_obs.i_slices["enemies.ids"]]
    living = [i for i in range(MAX_ENEMIES) if enemy_ids[i] != 0]
    assert len(living) >= 2, "fixture sanity: need >=2 living enemies"
    target = living[0]

    ef_sl = layout_obs.f_slices["enemies.f"]
    n_float = (ef_sl.stop - ef_sl.start) // MAX_ENEMIES

    obs_b = _copy_obs(obs)
    view = obs_b["f"][ef_sl].reshape(MAX_ENEMIES, n_float)
    view[target, 18:24] += 0.3

    with torch.no_grad():
        pair_a = model.actor_encoder.play_pair_features(
            _to_tobs(obs), "damage_matrix", "enemies.f", MAX_HAND, MAX_ENEMIES)[0]
        pair_b = model.actor_encoder.play_pair_features(
            _to_tobs(obs_b), "damage_matrix", "enemies.f", MAX_HAND, MAX_ENEMIES)[0]

    delta = (pair_b - pair_a).abs()   # (MAX_HAND, MAX_ENEMIES, 7)

    # feature 0 (damage_matrix) is untouched by an enemies.f-only obs change.
    assert torch.equal(pair_a[..., 0], pair_b[..., 0])

    # features 1-6 (the preview): identical across the HAND axis at the
    # target column (broadcast, not per-card) --
    target_col = delta[:, target, 1:]   # (MAX_HAND, 6)
    assert (target_col > 1e-6).all(), "the target column's preview features must all move"
    assert torch.allclose(target_col, target_col[0:1].expand_as(target_col)), (
        "the preview must be IDENTICAL across the hand axis -- it is a "
        "per-enemy property broadcast, not a per-(card, enemy) one")

    # -- and exactly zero everywhere else.
    for e in range(MAX_ENEMIES):
        if e == target:
            continue
        assert torch.equal(delta[:, e, 1:], torch.zeros_like(delta[:, e, 1:])), (
            f"enemy {e}'s pair feature must be untouched by enemy {target}'s "
            f"preview change")


# ── 11. R9: run-env variant of the damage_matrix liveness test ──────────

_RUN_DRIVE_SEED = 0
_RUN_DRIVE_STEP_BOUND = 100


def _drive_run_env_to_combat(seed: int = _RUN_DRIVE_SEED, bound: int = _RUN_DRIVE_STEP_BOUND):
    """Bounded, seed-fixed drive to a COMBAT decision inside `STS2RunEnv` --
    mirrors `test_tied_head_run.py`'s own helper and its module docstring's
    caveat about `env.step()`'s known rare indefinite hang (owned by
    another workstream): one fixed seed, a step bound well under 200, loud
    failure (a plain assert) instead of a silent skip or an unattended
    rollout."""
    from sts2_rl.driver import DecisionKind
    from sts2_rl.run_env import STS2RunEnv

    env = STS2RunEnv()
    obs, _info = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    for _ in range(bound):
        if env._request is not None and env._request.kind == DecisionKind.COMBAT:
            return env, obs
        mask = env.action_masks()
        obs, _reward, term, trunc, _info = env.step(int(rng.choice(np.flatnonzero(mask))))
        assert not (term or trunc), "episode ended before reaching a combat decision"
    raise AssertionError(
        f"COMBAT not reached within {bound} steps at seed={seed} -- either "
        f"the fixture premise (combat arrives quickly under masked-random "
        f"play) is wrong, or something regressed the driver's early-game "
        f"pacing.")


def test_run_env_damage_matrix_reaches_play_logits():
    """R9 brief test 4: the run-env variant of
    `test_damage_matrix_reaches_play_logits` -- same pair-tensor-zeroing
    mechanism and the same report finding (see that test's docstring) --
    against a real combat-phase `STS2RunEnv` obs. `combat.damage_matrix` is
    the literal segment name `run_action_layout`'s
    `play_pair_feature_segments` carries; unlike the combat env's variant,
    this test never even needs to name it directly -- the monkeypatch
    targets `play_pair_features` regardless of which segment names the
    layout resolved."""
    from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS

    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    obs_dim = (sum(w for _, w in f_segments), sum(w for _, w in i_segments))
    model = make_model(ModelSpec("run", arch="entset", hidden=(32,)), obs_dim, RUN_N_ACTIONS)

    env, obs = _drive_run_env_to_combat()
    tobs = _to_tobs(obs)
    mask_all = _all_legal_mask(RUN_N_ACTIONS)

    real_play_pair_features = model.actor_encoder.play_pair_features

    def _zeroed_pair(obs_arg, dm_name, enemy_f_name, S, T):
        return torch.zeros_like(real_play_pair_features(obs_arg, dm_name, enemy_f_name, S, T))

    with torch.no_grad():
        logits_real = model.action_logits(tobs, mask_all)[0]
        model.actor_encoder.play_pair_features = _zeroed_pair
        try:
            logits_zeroed_pair = model.action_logits(tobs, mask_all)[0]
        finally:
            model.actor_encoder.play_pair_features = real_play_pair_features

    play_delta = (logits_real[PLAY_BASE:POTION_BASE]
                  - logits_zeroed_pair[PLAY_BASE:POTION_BASE]).abs()
    assert play_delta.max() > 2e-5

    # Everything past the play block (potion_pairs, CHOICE, SELECT, belt-
    # POTION) never reads the play pair tensor -- same obs, same ctx, so
    # all of it must come out bit-identical, not just the potion range.
    assert torch.equal(logits_real[0], logits_zeroed_pair[0])
    assert torch.equal(logits_real[POTION_BASE:], logits_zeroed_pair[POTION_BASE:])
