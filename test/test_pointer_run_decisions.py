"""Tests for R8 ("pointer scoring for content-carrying run decisions"):
`sts2_rl/models.py`'s `ActionLayout.pointer_blocks`/`choice_row_overlays`/
`choice_float_overlays` + `EntitySetActorCritic` head assembly, and
`sts2_rl/action_heads.PointerHead`/`FloatPointerHead` wired end to end
against `STS2RunEnv`.

Real SHOP/REWARD_CARD/MAP observations are captured by driving `STS2RunEnv`
with ONE fixed seed under a bounded masked-random policy that prefers a
non-end-turn COMBAT action when one is legal (a plain uniform masked-random
policy, as the R8 census used, dies before reaching SHOP at seed 0 under
this file's own combat RNG draw order -- this is a fixture-only deviation
from the census's own probe, not a claim that either policy is "the"
canonical masked-random policy).

`env.step()` has a known rare indefinite hang (owned by another
workstream): every drive here uses ONE fixed seed, a step bound well under
200, and fails loudly (a plain `assert`, not a skip) if the target decision
isn't reached within that bound -- never loops over seeds or runs an
unattended rollout.

Two swap-test methodologies are used, deliberately different, because the
underlying pooling differs:

* SELECT/belt-POTION/SHOP-cards/SHOP-relics/SHOP-potions/REWARD-cards are
  entity ROW BLOCKS: `_EntsetEncoder.encode` pools them via `sum(dim=-2)`
  over their own rows before feeding the actor trunk, so swapping two rows
  WITHIN one block leaves that block's sum -- hence `pooled`/`ctx`, hence
  every OTHER logit -- bit-identical (`float` addition is commutative).
  Editing the real observation and re-running the whole `action_logits`
  pipeline is therefore a clean, end-to-end swap-equivariance test.
* MAP is different: `map0`..`map6` are seven SEPARATE raw `.f` segments,
  concatenated into `pooled` at fixed column positions (not summed
  together) -- `_EntsetEncoder`'s per-segment raw pass-through, not a row
  block. Swapping two of them in the real observation therefore changes
  `pooled`, hence `ctx`, hence (in principle) every logit, not just the two
  swapped CHOICE slots. `test_map_option_content_moves_choice_logits` below
  uses the same direct-head-invocation style as
  `test_out_of_phase_overlays_inert` (call `FloatPointerHead` directly with
  ONE shared `ctx`) to isolate the overlay's own row-equivariance from that
  upstream ctx effect, plus a weaker end-to-end sanity check that the real
  obs edit does move the corresponding CHOICE logits.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
import torch

from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.driver import DecisionKind
from sts2_rl.models import (
    EntitySetActorCritic,
    _validate_action_layout,
    run_action_layout,
)
from sts2_rl.run_env import (
    CHOICE_BASE,
    MAP_SLOTS,
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    N_ACTIONS,
    POTION_BASE,
    REWARD_CARD_SLOTS,
    SELECT_BASE,
    SHOP_CARD_SLOTS,
    SHOP_POTION_SLOTS,
    SHOP_RELIC_SLOTS,
    STS2RunEnv,
    run_obs_layout,
)
from sts2_rl.tensor_obs import TensorObs

_DRIVE_SEED = 0
_DRIVE_STEP_BOUND = 100


def _build_model(hidden=(32,)) -> EntitySetActorCritic:
    spec = ModelSpec("run", arch="entset", hidden=hidden)
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    model = make_model(spec, obs_dim, N_ACTIONS)
    assert isinstance(model, EntitySetActorCritic)
    return model


def _to_tobs(obs: dict) -> TensorObs:
    return TensorObs.from_dict(obs, device="cpu")[None]


def _copy_obs(obs: dict) -> dict:
    return {"f": np.array(obs["f"], copy=True), "i": np.array(obs["i"], copy=True)}


def _all_legal_mask(n: int = N_ACTIONS) -> torch.Tensor:
    return torch.ones(1, n, dtype=torch.bool)


def _swap_row(half: np.ndarray, sl: slice, cap: int, r1: int, r2: int) -> None:
    width = sl.stop - sl.start
    stride = width // cap
    view = half[sl].reshape(cap, stride)
    view[[r1, r2]] = view[[r2, r1]]


def _drive_to(kind: DecisionKind, seed: int = _DRIVE_SEED, bound: int = _DRIVE_STEP_BOUND):
    """Drive `STS2RunEnv` with a masked-random policy that prefers a
    non-end-turn COMBAT action when one is legal, until `kind` is reached,
    or fail loudly. Returns `(env, obs)` at that point -- see module
    docstring for why this file's own drive differs from a plain uniform
    masked-random policy."""
    env = STS2RunEnv()
    obs, _info = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    for step in range(bound):
        req = env._request
        if req is not None and req.kind == kind:
            return env, obs
        mask = env.action_masks()
        legal = np.flatnonzero(mask)
        if req is not None and req.kind == DecisionKind.COMBAT and len(legal) > 1 and legal[0] == 0:
            action = int(rng.choice(legal[1:]))
        else:
            action = int(rng.choice(legal))
        obs, _reward, term, trunc, _info = env.step(action)
        assert not (term or trunc), (
            f"episode ended before reaching {kind} (seed={seed}, step={step})")
    raise AssertionError(
        f"{kind} not reached within {bound} steps at seed={seed} -- either "
        f"the fixture premise is wrong, or something regressed the "
        f"driver's early-game pacing.")


# ── 1. layout tiling still exact under the R8 extensions ────────────────


def test_layout_tiling_still_exact():
    layout = run_action_layout()
    _validate_action_layout(layout)   # must not raise

    # Poke a choice_row_overlays entry outside the CHOICE range [0, 16).
    bad_row = replace(
        layout,
        choice_row_overlays=layout.choice_row_overlays + ((14, 3, "shop.relics", 0),),
    )
    with pytest.raises(ValueError):
        _validate_action_layout(bad_row)

    # Poke a choice_float_overlays entry outside the CHOICE range too.
    bad_float = replace(layout, choice_float_overlays=((16, 1, "shop.removal"),))
    with pytest.raises(ValueError):
        _validate_action_layout(bad_float)


# ── 2. SELECT-by-candidate pointer block (synthetic obs edit) ───────────


def test_select_candidates_swap_equivariance():
    model = _build_model()
    env = STS2RunEnv()
    obs, _info = env.reset(seed=_DRIVE_SEED)
    L = run_obs_layout()
    obs = _copy_obs(obs)

    ids_sl = L.i_slices["select.candidates.ids"]
    f_sl = L.f_slices["select.candidates.f"]
    cap = MAX_SELECT_CANDIDATES
    ids_view = obs["i"][ids_sl].reshape(cap, 4)
    f_view = obs["f"][f_sl].reshape(cap, 4)
    ids_view[:] = 0
    f_view[:] = 0.0
    r1, r2 = 0, 1
    ids_view[r1] = [0, 5, 0, 0]
    f_view[r1] = [1.0, 0.3, 0.0, 0.0]
    ids_view[r2] = [0, 9, 0, 0]
    f_view[r2] = [1.0, 0.7, 0.0, 0.0]

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], ids_sl, cap, r1, r2)
    _swap_row(obs_b["f"], f_sl, cap, r1, r2)

    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]

    assert torch.allclose(logits_b[SELECT_BASE + r1], logits_a[SELECT_BASE + r2], atol=1e-5)
    assert torch.allclose(logits_b[SELECT_BASE + r2], logits_a[SELECT_BASE + r1], atol=1e-5)
    assert not torch.allclose(logits_a[SELECT_BASE + r1], logits_a[SELECT_BASE + r2], atol=1e-6), (
        "fixture sanity: the two rows must actually score differently")
    for r in range(cap):
        if r in (r1, r2):
            continue
        assert torch.allclose(logits_b[SELECT_BASE + r], logits_a[SELECT_BASE + r], atol=1e-5), r
    # Every non-SELECT logit is untouched too (select.candidates is summed
    # into pooled, so a within-block swap leaves ctx exactly unchanged).
    assert torch.allclose(logits_a[:SELECT_BASE], logits_b[:SELECT_BASE], atol=1e-5)
    assert torch.allclose(
        logits_a[SELECT_BASE + cap:], logits_b[SELECT_BASE + cap:], atol=1e-5)


# ── 3. belt-POTION pointer block (synthetic obs edit) ────────────────────


def test_belt_potion_swap_equivariance():
    model = _build_model()
    env = STS2RunEnv()
    obs, _info = env.reset(seed=_DRIVE_SEED)
    L = run_obs_layout()
    obs = _copy_obs(obs)

    ids_sl = L.i_slices["run.potions.ids"]
    f_sl = L.f_slices["run.potions.f"]
    cap = MAX_POTION_SLOTS
    ids_view = obs["i"][ids_sl].reshape(cap, 1)
    f_view = obs["f"][f_sl].reshape(cap, 2)
    r1, r2 = 0, 1
    ids_view[r1] = [3]
    f_view[r1] = [1.0, 1.0]
    ids_view[r2] = [7]
    f_view[r2] = [1.0, 1.0]

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], ids_sl, cap, r1, r2)
    _swap_row(obs_b["f"], f_sl, cap, r1, r2)

    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]

    assert torch.allclose(logits_b[POTION_BASE + r1], logits_a[POTION_BASE + r2], atol=1e-5)
    assert torch.allclose(logits_b[POTION_BASE + r2], logits_a[POTION_BASE + r1], atol=1e-5)
    assert not torch.allclose(logits_a[POTION_BASE + r1], logits_a[POTION_BASE + r2], atol=1e-6)
    for r in range(cap):
        if r in (r1, r2):
            continue
        assert torch.allclose(logits_b[POTION_BASE + r], logits_a[POTION_BASE + r], atol=1e-5), r


# ── 4. SHOP: card-row overlay moves the right CHOICE slots (real obs) ───


def test_shop_card_swap_moves_choice_logits():
    model = _build_model()
    env, obs = _drive_to(DecisionKind.SHOP)
    L = run_obs_layout()
    obs = _copy_obs(obs)

    ids_sl = L.i_slices["shop.cards.ids"]
    f_sl = L.f_slices["shop.cards.f"]
    cap = SHOP_CARD_SLOTS
    ids_view = obs["i"][ids_sl].reshape(cap, 1)
    assert ids_view[0, 0] != 0 and ids_view[1, 0] != 0 and ids_view[0, 0] != ids_view[1, 0], (
        "fixture sanity: need two distinct real shop.cards rows")

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], ids_sl, cap, 0, 1)
    _swap_row(obs_b["f"], f_sl, cap, 0, 1)

    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]

    c0, c1 = CHOICE_BASE + 0, CHOICE_BASE + 1
    # Sum invariance under swap.
    assert torch.allclose(logits_a[c0] + logits_a[c1], logits_b[c0] + logits_b[c1], atol=1e-5)
    # It actually MOVED -- a positional-only head would leave c0/c1 bit-
    # identical between A and B (ctx doesn't change: shop.cards is a
    # masked-sum-pooled row block, permutation-invariant to a within-block
    # swap). This is the assertion a positional-only head FAILS.
    assert not torch.allclose(logits_a[c0], logits_b[c0], atol=1e-6)
    assert not torch.allclose(logits_a[c1], logits_b[c1], atol=1e-6)
    # Every other logit (including CHOICE slots 2-15) is untouched.
    for idx in range(logits_a.shape[0]):
        if idx in (c0, c1):
            continue
        assert torch.allclose(logits_a[idx], logits_b[idx], atol=1e-5), idx


def test_shop_relic_swap_lands_at_slot_7_and_8_not_6_or_9():
    """Mutation check (b) from the R8 brief, promoted to a permanent
    assertion: an off-by-one `choice_slot_base_offset` for the shop.relics
    overlay (6 instead of the census-verified 7) would leak a relic-row-0/1
    swap into CHOICE slots 6/7 instead of 7/8 -- this test fails under that
    mutation and passes under the correct offset. Uses a within-block SWAP
    (not a PAD/removal edit) so `ctx` stays exactly invariant, same
    reasoning as test 4 -- a value-removing edit changes the block's row
    SUM and contaminates every logit a little, which would make a "slot 6
    untouched" assertion meaningless."""
    model = _build_model()
    env, obs = _drive_to(DecisionKind.SHOP)
    L = run_obs_layout()
    obs = _copy_obs(obs)

    ids_sl = L.i_slices["shop.relics.ids"]
    f_sl = L.f_slices["shop.relics.f"]
    cap = SHOP_RELIC_SLOTS
    ids_view = obs["i"][ids_sl].reshape(cap, 1)
    assert ids_view[0, 0] != 0 and ids_view[1, 0] != 0 and ids_view[0, 0] != ids_view[1, 0], (
        "fixture sanity: need two distinct real shop.relics rows")

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], ids_sl, cap, 0, 1)
    _swap_row(obs_b["f"], f_sl, cap, 0, 1)

    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]

    slot6, slot7, slot8, slot9 = (
        CHOICE_BASE + 6, CHOICE_BASE + 7, CHOICE_BASE + 8, CHOICE_BASE + 9)
    assert not torch.allclose(logits_a[slot7], logits_b[slot7], atol=1e-6), (
        "shop.relics row 0 must overlay onto CHOICE slot 7 (R8 census: "
        "relic slots are 7-9)")
    assert not torch.allclose(logits_a[slot8], logits_b[slot8], atol=1e-6)
    assert torch.allclose(logits_a[slot6], logits_b[slot6], atol=1e-6), (
        "CHOICE slot 6 (shop.cards row 6) must be untouched by a "
        "shop.relics-only swap -- an off-by-one overlay offset (relics at "
        "6 instead of 7) would leak into slot 6 instead of slot 7")
    assert torch.allclose(logits_a[slot9], logits_b[slot9], atol=1e-6)


# ── 5. REWARD_CARD: card-row overlay moves CHOICE logit 0 (real obs) ────


def test_reward_card_rows_move_choice_logits():
    model = _build_model()
    env, obs = _drive_to(DecisionKind.REWARD_CARD)
    L = run_obs_layout()
    obs = _copy_obs(obs)

    ids_sl = L.i_slices["reward.cards.ids"]
    f_sl = L.f_slices["reward.cards.f"]
    cap = REWARD_CARD_SLOTS
    ids_view = obs["i"][ids_sl].reshape(cap, 4)
    assert ids_view[0, 1] != 0 and ids_view[1, 1] != 0 and ids_view[0, 1] != ids_view[1, 1], (
        "fixture sanity: need two distinct real reward.cards rows")

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], ids_sl, cap, 0, 1)
    _swap_row(obs_b["f"], f_sl, cap, 0, 1)

    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]

    c0, c1 = CHOICE_BASE + 0, CHOICE_BASE + 1
    assert torch.allclose(logits_a[c0] + logits_a[c1], logits_b[c0] + logits_b[c1], atol=1e-5)
    assert not torch.allclose(logits_a[c0], logits_b[c0], atol=1e-6)
    for idx in range(logits_a.shape[0]):
        if idx in (c0, c1):
            continue
        assert torch.allclose(logits_a[idx], logits_b[idx], atol=1e-5), idx


# ── 6. out-of-phase overlays are inert (presence gating, real shop obs) ──


def test_out_of_phase_overlays_inert():
    """On a real SHOP obs, `reward.cards` rows and every `map{k}` segment
    are PAD/zero (a shop decision carries no reward-card or map content).
    Calling the corresponding overlay heads directly (least invasive: no
    private-method surface needed beyond what `_choice_overlay` already
    uses internally) must give an EXACT zero contribution, not merely a
    small one -- T7/R8's presence-gating invariant."""
    model = _build_model()
    env, obs = _drive_to(DecisionKind.SHOP)
    layout = model.action_layout
    tobs = _to_tobs(obs)

    with torch.no_grad():
        pooled, rows = model.actor_encoder.encode(tobs)
        ctx = model.actor(pooled)

        reward_idx = next(
            i for i, e in enumerate(layout.choice_row_overlays) if e[2] == "reward.cards")
        _offset, n_slots, row_block, row_offset = layout.choice_row_overlays[reward_idx]
        reward_rows = rows[row_block][..., row_offset:row_offset + n_slots, :]
        assert torch.equal(reward_rows, torch.zeros_like(reward_rows)), (
            "fixture sanity: reward.cards must be PAD on a SHOP obs")
        reward_scores = model.choice_row_overlay_heads[reward_idx](reward_rows, ctx)
        assert torch.equal(reward_scores, torch.zeros_like(reward_scores))

        map_idx = next(
            i for i, e in enumerate(layout.choice_float_overlays) if e[2] == "map")
        names = model._choice_float_seg_names[map_idx]
        seg = torch.stack([model.actor_encoder.raw(tobs, n) for n in names], dim=-2)
        assert torch.equal(seg, torch.zeros_like(seg)), (
            "fixture sanity: every map{k} segment must be zero on a SHOP obs")
        map_scores = model.choice_float_overlay_heads[map_idx](seg, ctx)
        assert torch.equal(map_scores, torch.zeros_like(map_scores))


# ── 7. MAP option content moves the CHOICE overlay (real obs) ───────────


def test_map_option_content_moves_choice_logits():
    """See module docstring: `map0`..`map6` are raw, positionally-
    concatenated `.f` segments (not a summed row block), so swapping them
    in the real observation perturbs `ctx` itself -- unlike tests 2-5. This
    test isolates the overlay's own row-equivariance with ONE shared `ctx`
    (direct-head-invocation, same style as test 6), then adds a weaker
    end-to-end sanity check that the real obs edit does move the
    corresponding CHOICE logits."""
    model = _build_model()
    env, obs = _drive_to(DecisionKind.MAP)
    L = run_obs_layout()

    r1, r2 = 0, 2
    names = [f"map{m}" for m in range(MAP_SLOTS)]
    f = np.asarray(obs["f"])
    seg1 = f[L.f_slices[names[r1]]]
    seg2 = f[L.f_slices[names[r2]]]
    assert seg1.any() and seg2.any() and not np.array_equal(seg1, seg2), (
        "fixture sanity: need two nonzero, distinct map slots")

    tobs = _to_tobs(obs)
    layout = model.action_layout
    with torch.no_grad():
        pooled, rows = model.actor_encoder.encode(tobs)
        ctx = model.actor(pooled)
        map_idx = next(
            i for i, e in enumerate(layout.choice_float_overlays) if e[2] == "map")
        head = model.choice_float_overlay_heads[map_idx]
        seg_a = torch.stack([model.actor_encoder.raw(tobs, n) for n in names], dim=-2)
        scores_a = head(seg_a, ctx)

        perm = list(range(MAP_SLOTS))
        perm[r1], perm[r2] = perm[r2], perm[r1]
        seg_b = seg_a[..., perm, :]
        scores_b = head(seg_b, ctx)

    assert torch.allclose(scores_b, scores_a[..., perm], atol=1e-6)
    assert not torch.allclose(scores_a[..., r1], scores_a[..., r2], atol=1e-6), (
        "fixture sanity: the two map slots must actually score differently")

    # Weaker end-to-end sanity: editing the real obs and re-running the
    # whole pipeline does move the two corresponding CHOICE logits (ctx
    # drift notwithstanding).
    obs_b = _copy_obs(obs)
    obs_b["f"][L.f_slices[names[r1]]] = seg2
    obs_b["f"][L.f_slices[names[r2]]] = seg1
    mask = _all_legal_mask()
    with torch.no_grad():
        logits_a = model.action_logits(tobs, mask)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask)[0]
    c0, c2 = CHOICE_BASE + r1, CHOICE_BASE + r2
    assert not torch.allclose(logits_a[c0], logits_b[c0], atol=1e-6)
    assert not torch.allclose(logits_a[c2], logits_b[c2], atol=1e-6)


# ── 8. combat regression: combat_action_layout untouched by R8 ──────────


def test_combat_action_layout_has_no_r8_fields():
    from sts2_rl.full_env import MAX_POTIONS
    from sts2_rl.models import combat_action_layout

    layout = combat_action_layout(MAX_POTIONS)
    assert layout.pointer_blocks == ()
    assert layout.choice_base is None
    assert layout.choice_row_overlays == ()
    assert layout.choice_float_overlays == ()
