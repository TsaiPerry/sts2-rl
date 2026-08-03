"""Tests for `_EntsetEncoder.encode` (sts2_rl/models.py) -- the enabling
refactor for the phase-2 tied action head (T7 brief). `encode(obs)` must
return `(pooled, rows)`: `pooled` bit-identical to today's `forward(obs)`,
and `rows` the per-row-block, mask-multiplied row tensors `forward` used to
discard right after summing them.

Fixtures follow `test/test_models.py`'s own `test_entset_*` pattern: a REAL
env observation (`STS2FullCombatEnv`/`STS2RunEnv` `.reset(seed=0)`), not a
synthetic tensor, because the encoder depends on the layout's actual
segment names/widths and the row-block key behaviour is exactly what's
under test.
"""
from __future__ import annotations

import numpy as np
import torch

from sts2_rl.checkpoints import ModelSpec, model_obs_layout
from sts2_rl.full_env import (
    MAX_ENEMIES,
    MAX_HAND,
    MAX_POTION_ROWS,
    MAX_POTIONS,
    STS2FullCombatEnv,
    combat_obs_layout,
)
from sts2_rl.models import EntitySetActorCritic, combat_action_layout, entset_segment_plan, run_action_layout
from sts2_rl.run_env import STS2RunEnv, run_obs_layout
from sts2_rl.tensor_obs import TensorObs

COMBAT_N_ACTIONS = 79
RUN_N_ACTIONS_HIDDEN = (32,)


def _combat_encoder_and_obs():
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    model = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, combat_action_layout(MAX_POTIONS), hidden=(32,))
    env = STS2FullCombatEnv()
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]
    return model.actor_encoder, tobs, obs, f_segments, i_segments


def test_encode_pooled_identical_to_forward():
    encoder, tobs, _obs, _f, _i = _combat_encoder_and_obs()
    with torch.no_grad():
        pooled, rows = encoder.encode(tobs)
        forwarded = encoder.forward(tobs)
    assert torch.equal(pooled, forwarded)
    assert isinstance(rows, dict) and rows, "encode must also return non-empty rows"


def test_encode_row_block_shapes():
    encoder, tobs, _obs, _f, _i = _combat_encoder_and_obs()
    with torch.no_grad():
        _pooled, rows = encoder.encode(tobs)
    block_dim = encoder.block_dim
    assert rows["hand"].shape == (1, MAX_HAND, block_dim)
    assert rows["enemies"].shape == (1, MAX_ENEMIES, block_dim)
    assert rows["potions"].shape == (1, MAX_POTION_ROWS, block_dim)


def test_pad_rows_are_zero_vectors():
    """Recompute presence straight from the raw obs per OBS_SCHEMA.md
    Sec.2.1 (primary vocab id != 0, OR'd with any-float-nonzero when the
    block has floats -- the encoder's own rule, see
    `_EntsetEncoder.encode`'s comment), then assert absent rows are an
    EXACT zero vector in `rows` and at least one present row is nonzero."""
    encoder, tobs, obs, f_segments, i_segments = _combat_encoder_and_obs()
    # `_layer_init` zeroes every proj layer's bias, so at a fresh init
    # `tanh(proj(all-zero-row))` is ALREADY 0 regardless of masking -- that
    # would make this test pass even against a mutant that forgets to mask
    # entirely. Force a nonzero bias on every row-block projection so the
    # zero-vector property in `rows` can only come from the multiply-by-mask,
    # not from init luck.
    with torch.no_grad():
        for proj in encoder._blocks:
            proj.bias.fill_(0.37)
        _pooled, rows = encoder.encode(tobs)

    layout = combat_obs_layout()
    row_blocks, _raw = entset_segment_plan(f_segments, i_segments)

    checked_any_present = False
    any_nonzero_present = False
    for name, cap, n_float, vocabs in row_blocks:
        n_int = len(vocabs)
        i_slice = layout.i_slices[name]
        ids = np.asarray(obs["i"])[i_slice].reshape(cap, n_int)
        primary = next(idx for idx, v in enumerate(vocabs) if v is not None)
        present = ids[:, primary] != 0
        if n_float:
            f_name = f"{name[:-len('.ids')]}.f"
            f_slice = layout.f_slices[f_name]
            floats = np.asarray(obs["f"])[f_slice].reshape(cap, n_float)
            present = present | (floats != 0).any(axis=-1)

        logical = name[: -len(".ids")]
        if logical.startswith("combat."):
            logical = logical[len("combat."):]
        row_tensor = rows[logical][0]  # (cap, block_dim), batch dim 0
        assert row_tensor.shape[0] == cap

        for r in range(cap):
            if present[r]:
                checked_any_present = True
                if row_tensor[r].abs().sum().item() > 0:
                    any_nonzero_present = True
            else:
                assert torch.equal(
                    row_tensor[r], torch.zeros_like(row_tensor[r])
                ), f"{logical!r} row {r} is PAD but not an exact zero vector"

    assert checked_any_present, "fixture sanity: at least one row must be present"
    # At least one PRESENT row must be nonzero somewhere (sanity that the
    # mask isn't accidentally zeroing everything, e.g. an inverted mask).
    assert any_nonzero_present, "every present row pooled to exactly zero -- suspicious"


def test_rows_keys_match_segment_plan():
    encoder, tobs, _obs, f_segments, i_segments = _combat_encoder_and_obs()
    with torch.no_grad():
        _pooled, rows = encoder.encode(tobs)

    row_blocks, _raw = entset_segment_plan(f_segments, i_segments)
    expected = set()
    for name, _cap, _n_float, _vocabs in row_blocks:
        logical = name[: -len(".ids")]
        if logical.startswith("combat."):
            logical = logical[len("combat."):]
        expected.add(logical)

    assert set(rows) == expected


def test_encode_run_layout_row_block_shapes():
    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS

    model = EntitySetActorCritic(
        f_segments, i_segments, RUN_N_ACTIONS, run_action_layout(), hidden=(32,))
    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]

    with torch.no_grad():
        pooled, rows = model.actor_encoder.encode(tobs)
        forwarded = model.actor_encoder.forward(tobs)
    assert torch.equal(pooled, forwarded)

    block_dim = model.actor_encoder.block_dim
    assert rows["hand"].shape == (1, MAX_HAND, block_dim)
    assert rows["enemies"].shape == (1, MAX_ENEMIES, block_dim)
    assert rows["run.potions"].shape == (1, MAX_POTION_ROWS, block_dim)


def test_encode_run_layout_rows_keys_match_segment_plan():
    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS

    model = EntitySetActorCritic(
        f_segments, i_segments, RUN_N_ACTIONS, run_action_layout(), hidden=(32,))
    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]

    with torch.no_grad():
        _pooled, rows = model.actor_encoder.encode(tobs)

    row_blocks, _raw = entset_segment_plan(f_segments, i_segments)
    expected = set()
    for name, _cap, _n_float, _vocabs in row_blocks:
        logical = name[: -len(".ids")]
        if logical.startswith("combat."):
            logical = logical[len("combat."):]
        expected.add(logical)

    assert set(rows) == expected
    # The run-env layout folds a whole combat block in under "combat." --
    # confirm the prefix stripping actually collapsed those keys onto the
    # SAME logical names the combat env itself uses (e.g. "hand", not
    # "combat.hand"), rather than the test accidentally not exercising it.
    assert "hand" in expected and "combat.hand" not in expected
    assert "run.potions" in expected
