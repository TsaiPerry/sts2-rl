"""Tests for the run/curriculum envs' tied action head (T7 brief §3/§4,
phase-2 Task 4): the SAME combat pointer heads as
`test/test_tied_head_combat.py`, scoring the embedded `combat.*` block,
with CHOICE/SELECT/belt-POTION still positional. Built via
`checkpoints.make_model` -- the production wiring path -- for both
`env_kind="run"` and `"column"` (they share one layout/action space).

`env.step()` has a known rare indefinite hang (owned by another
workstream): every drive of `STS2RunEnv` here uses ONE fixed seed, a
step bound well under 200, and fails loudly (a plain `assert`, not a
skip) if combat isn't reached within that bound -- never loops over seeds
or runs an unattended rollout.
"""
from __future__ import annotations

import numpy as np
import torch

from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.driver import DecisionKind
from sts2_rl.full_env import MAX_ENEMIES, MAX_HAND
from sts2_rl.models import EntitySetActorCritic, run_action_layout
from sts2_rl.run_env import (
    CHOICE_BASE,
    CHOICE_SLOTS,
    MAX_POTION_SLOTS,
    MAX_SELECT_CANDIDATES,
    N_ACTIONS,
    POTION_BASE,
    SELECT_BASE,
    STS2RunEnv,
    run_obs_layout,
)
from sts2_rl.tensor_obs import TensorObs

# Bounded, seed-fixed drive to a COMBAT decision -- see module docstring on
# the run-env step() hang.
_DRIVE_SEED = 0
_DRIVE_STEP_BOUND = 100

PLAY_BASE = 1
COMBAT_POTION_BASE = PLAY_BASE + MAX_HAND * MAX_ENEMIES   # 61 -- N_COMBAT_ACTIONS = 121


def _obs_dim(env_kind: str) -> tuple[int, int]:
    f_segments, i_segments = model_obs_layout(ModelSpec(env_kind, arch="entset"))
    return sum(w for _, w in f_segments), sum(w for _, w in i_segments)


def _build_via_make_model(env_kind: str, hidden=(32,)) -> EntitySetActorCritic:
    obs_dim = _obs_dim(env_kind)
    model = make_model(ModelSpec(env_kind, arch="entset", hidden=hidden), obs_dim, N_ACTIONS)
    assert isinstance(model, EntitySetActorCritic)
    return model


def _drive_to_combat(seed: int = _DRIVE_SEED, bound: int = _DRIVE_STEP_BOUND):
    """Step `STS2RunEnv` with masked-random legal actions until a COMBAT
    decision arrives, or fail loudly. Returns `(env, obs)` at that point."""
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


def _to_tobs(obs: dict) -> TensorObs:
    return TensorObs.from_dict(obs, device="cpu")[None]


def _copy_obs(obs: dict) -> dict:
    return {"f": np.array(obs["f"], copy=True), "i": np.array(obs["i"], copy=True)}


def _swap_row(half: np.ndarray, sl: slice, cap: int, r1: int, r2: int) -> None:
    width = sl.stop - sl.start
    stride = width // cap
    view = half[sl].reshape(cap, stride)
    view[[r1, r2]] = view[[r2, r1]]


def _all_legal_mask(n: int) -> torch.Tensor:
    return torch.ones(1, n, dtype=torch.bool)


# ── 7. layout tiling via the production wiring path ─────────────────────


def test_make_model_builds_243_wide_tiled_layout():
    for env_kind in ("run", "column"):
        model = _build_via_make_model(env_kind)
        assert model.n_actions == N_ACTIONS == 243

        # Mutation check (b) (see test_tied_head_combat.py's twin assertion):
        # play and potion are separately-weighted PairPointerHead instances.
        assert model.play_head is not model.potion_head
        play_params = list(model.play_head.parameters())
        potion_params = list(model.potion_head.parameters())
        assert not all(torch.equal(a, b) for a, b in zip(play_params, potion_params))
        layout = model.action_layout
        assert layout.n_actions == 243
        _src, _tgt, S, T = layout.play
        _src2, _tgt2, S_used, T2 = layout.potion_pairs
        assert S * T == 60
        assert S_used * T2 == 60   # MAX_POTION_SLOTS(10) * MAX_ENEMIES(6)
        assert 1 + S * T + S_used * T2 == 121   # N_COMBAT_ACTIONS
        # R8: CHOICE keeps its positional Linear (plus additive content
        # overlays); SELECT and belt-POTION are REPLACED by pointer blocks
        # over their own entity rows (see run_action_layout's docstring).
        widths = [w for _base, w in layout.positional]
        assert widths == [CHOICE_SLOTS]
        pointer = [(base, w, block) for base, w, block in layout.pointer_blocks]
        assert pointer == [
            (SELECT_BASE, MAX_SELECT_CANDIDATES, "select.candidates"),
            (POTION_BASE, MAX_POTION_SLOTS, "run.potions"),
        ]
        assert 121 + CHOICE_SLOTS + MAX_SELECT_CANDIDATES + MAX_POTION_SLOTS == 243

        env = STS2RunEnv()
        obs, _info = env.reset(seed=0)
        mask = torch.as_tensor(env.action_masks(), dtype=torch.bool).unsqueeze(0)
        tobs = _to_tobs(obs)
        logits = model.action_logits(tobs, mask)
        assert logits.shape == (1, 243)


# ── 8. combat-phase hand-swap equivariance inside the run env ───────────


def test_run_combat_phase_hand_swap():
    model = _build_via_make_model("run")
    env, obs = _drive_to_combat()
    assert env._request is not None and env._request.kind == DecisionKind.COMBAT

    layout_obs = run_obs_layout()
    hand_ids = np.asarray(obs["i"])[layout_obs.i_slices["combat.hand.ids"]].reshape(MAX_HAND, 3)[:, 0]
    pair = None
    for a in range(MAX_HAND):
        for b in range(a + 1, MAX_HAND):
            if hand_ids[a] != 0 and hand_ids[b] != 0 and hand_ids[a] != hand_ids[b]:
                pair = (a, b)
                break
        if pair:
            break
    assert pair is not None, "fixture sanity: need two hand slots with different card ids"
    h1, h2 = pair

    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], layout_obs.i_slices["combat.hand.ids"], MAX_HAND, h1, h2)
    _swap_row(obs_b["f"], layout_obs.f_slices["combat.hand.f"], MAX_HAND, h1, h2)
    # R9 (models.py `run_action_layout`'s play_pair_feature_segments): the
    # embedded combat block's `combat.damage_matrix` is now also a play-head
    # PAIR feature keyed on the hand axis -- swap its two rows too, same as
    # `test_tied_head_combat.py::test_hand_swap_equivariance`.
    _swap_row(obs_b["f"], layout_obs.f_slices["combat.damage_matrix"], MAX_HAND, h1, h2)

    mask_all = _all_legal_mask(N_ACTIONS)
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask_all)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask_all)[0]

    # R9: `combat.damage_matrix` was already a raw pooled feature feeding
    # `ctx` directly (T7/R8, unrelated to R9); swapping its rows (needed
    # above) perturbs `ctx` by a small residual amount that every logit
    # inherits uniformly -- see `test_tied_head_combat.py::
    # test_hand_swap_equivariance`'s twin comment/report entry for the
    # measured magnitude and why `atol=1e-5` (this file's usual bound) is
    # too tight now.
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

    # CHOICE / SELECT / belt-POTION (still positional, ctx-only): not
    # touched by the play-equivariance property (they don't permute), but
    # not bit-identical either, per the ctx-coupling note above.
    assert torch.allclose(logits_b[CHOICE_BASE:], logits_a[CHOICE_BASE:], atol=atol)
    assert torch.allclose(logits_b[0], logits_a[0], atol=atol)
    assert torch.allclose(
        logits_b[COMBAT_POTION_BASE:CHOICE_BASE], logits_a[COMBAT_POTION_BASE:CHOICE_BASE], atol=atol)


# ── 9. combat.* rows collapse onto the SAME logical keys as the combat env


def test_run_rows_have_both_combat_and_run_keys():
    model = _build_via_make_model("run")
    env, obs = _drive_to_combat()

    tobs = _to_tobs(obs)
    with torch.no_grad():
        _pooled, rows = model.actor_encoder.encode(tobs)

    assert "hand" in rows and "combat.hand" not in rows
    assert "enemies" in rows and "combat.enemies" not in rows
    assert "potions" in rows and "combat.potions" not in rows
    assert "run.deck" in rows
    assert "select.candidates" in rows
    assert "run.potions" in rows
