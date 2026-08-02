"""Tests for ``sts2_rl.tensor_obs.TensorObs`` -- OBS_SCHEMA.md §2.2's "one
place the break lives": a minimal (f, i) pair type so ``train_torch.py``'s
PPO loop text (``obs_buf[t] = next_obs``, ``b_obs.reshape(...)``,
``b_obs[mb]``) reads almost unchanged against the new ``{"f", "i"}``
observation contract.

The load-bearing property throughout is that the two halves stay ALIGNED
(same batch/row indexing) and TYPED (float32 stays float32, the int half
never silently promotes to float -- that would destroy every id, since an
embedding table indexes by exact integer value).
"""
from __future__ import annotations

import numpy as np
import pytest
import torch

from sts2_rl.tensor_obs import TensorObs


def make(f_shape=(4, 3), i_shape=(4, 2), seed=0):
    rng = np.random.default_rng(seed)
    f = rng.random(f_shape, dtype=np.float64).astype(np.float32)
    i = rng.integers(0, 50, size=i_shape).astype(np.int32)
    return TensorObs(f, i)


# ── construction ──────────────────────────────────────────────────────────


def test_from_dict_keeps_numpy_arrays_when_no_device_given():
    d = {"f": np.zeros(3, np.float32), "i": np.zeros(2, np.int32)}
    obs = TensorObs.from_dict(d)
    assert obs.f is d["f"]
    assert obs.i is d["i"]


def test_from_dict_with_device_builds_torch_tensors():
    d = {"f": np.array([1.0, 2.0], np.float32), "i": np.array([3, 4], np.int32)}
    obs = TensorObs.from_dict(d, device="cpu")
    assert torch.is_tensor(obs.f) and torch.is_tensor(obs.i)
    assert obs.f.dtype == torch.float32
    # int64/long: torch embedding lookups require it, and it is still an
    # exact-integer type -- no id-destroying float promotion.
    assert obs.i.dtype == torch.int64
    assert torch.equal(obs.f, torch.tensor([1.0, 2.0]))
    assert torch.equal(obs.i, torch.tensor([3, 4]))


# ── indexing ──────────────────────────────────────────────────────────────


def test_getitem_indexes_both_halves_in_lockstep():
    obs = make(f_shape=(5, 3), i_shape=(5, 2))
    sub = obs[[1, 3]]
    assert isinstance(sub, TensorObs)
    np.testing.assert_array_equal(sub.f, obs.f[[1, 3]])
    np.testing.assert_array_equal(sub.i, obs.i[[1, 3]])


def test_getitem_none_adds_a_leading_batch_axis():
    """The truncation-bootstrap call site: a single-env final obs needs a
    batch dim of 1 before it can go through the model."""
    obs = make(f_shape=(3,), i_shape=(2,))
    batched = obs[None]
    assert batched.f.shape == (1, 3)
    assert batched.i.shape == (1, 2)


def test_setitem_writes_both_halves_at_the_target_index():
    buf = TensorObs(np.zeros((4, 3), np.float32), np.zeros((4, 2), np.int32))
    row = make(f_shape=(3,), i_shape=(2,), seed=1)
    buf[2] = row
    np.testing.assert_array_equal(buf.f[2], row.f)
    np.testing.assert_array_equal(buf.i[2], row.i)
    # Untouched rows stay untouched.
    assert np.array_equal(buf.f[0], np.zeros(3, np.float32))


def test_setitem_does_not_cross_the_halves():
    """A bug that wrote obs.i into buf.f (or vice versa) would silently
    corrupt every id -- this pins that the two halves never swap."""
    buf = TensorObs(np.zeros((2, 3), np.float32), np.zeros((2, 2), np.int32))
    row = TensorObs(np.array([1.0, 1.0, 1.0], np.float32), np.array([9, 9], np.int32))
    buf[0] = row
    assert buf.f.dtype == np.float32 and buf.i.dtype == np.int32
    np.testing.assert_array_equal(buf.f[0], [1.0, 1.0, 1.0])
    np.testing.assert_array_equal(buf.i[0], [9, 9])


# ── reshape ───────────────────────────────────────────────────────────────


def test_reshape_splits_the_trailing_pair_per_half():
    """``obs_buf.reshape(-1, obs_dim)`` with ``obs_dim = (f_dim, i_dim)`` --
    the exact call shape train_torch.py's flatten-for-the-update step uses."""
    f = torch.arange(2 * 3 * 4, dtype=torch.float32).reshape(2, 3, 4)
    i = torch.arange(2 * 3 * 5, dtype=torch.int64).reshape(2, 3, 5)
    obs = TensorObs(f, i)
    flat = obs.reshape(-1, (4, 5))
    assert flat.f.shape == (6, 4)
    assert flat.i.shape == (6, 5)
    assert torch.equal(flat.f, f.reshape(-1, 4))
    assert torch.equal(flat.i, i.reshape(-1, 5))


def test_reshape_round_trips_values_not_just_shape():
    obs = make(f_shape=(2, 3), i_shape=(2, 2))
    flat = obs.reshape(-1, (3, 2))
    back = flat.reshape(2, -1, (3, 2))
    np.testing.assert_array_equal(back.f.reshape(2, 3), obs.f)
    np.testing.assert_array_equal(back.i.reshape(2, 2), obs.i)


# ── device movement ───────────────────────────────────────────────────────


def test_to_preserves_alignment_and_dtypes():
    obs = make(f_shape=(4, 3), i_shape=(4, 2))
    moved = obs.to("cpu")
    assert torch.is_tensor(moved.f) and torch.is_tensor(moved.i)
    assert moved.f.dtype == torch.float32
    assert moved.i.dtype == torch.int64
    np.testing.assert_array_equal(moved.f.numpy(), obs.f)
    np.testing.assert_array_equal(moved.i.numpy(), obs.i)


def test_to_is_idempotent_on_an_already_torch_backed_obs():
    obs = make(f_shape=(2, 2), i_shape=(2, 2)).to("cpu")
    moved_again = obs.to("cpu")
    assert torch.equal(moved_again.f, obs.f)
    assert torch.equal(moved_again.i, obs.i)


# ── copy ──────────────────────────────────────────────────────────────────


def test_copy_is_independent_of_the_source():
    obs = make(f_shape=(2, 2), i_shape=(2, 2))
    dup = obs.copy()
    dup.f[0, 0] = 999.0
    dup.i[0, 0] = 999
    assert obs.f[0, 0] != 999.0
    assert obs.i[0, 0] != 999


# ── equality (what makes generic np.array_equal(x, y) rollout comparisons
# work on a TensorObs without special-casing it in test code we don't own) ──


def test_array_equal_true_for_identical_content():
    a = make(seed=5)
    b = TensorObs(a.f.copy(), a.i.copy())
    assert np.array_equal(a, b)


def test_array_equal_false_when_the_float_half_differs():
    a = make(seed=5)
    b = TensorObs(a.f.copy(), a.i.copy())
    b.f[0, 0] += 1.0
    assert not np.array_equal(a, b)


def test_array_equal_false_when_the_int_half_differs():
    a = make(seed=5)
    b = TensorObs(a.f.copy(), a.i.copy())
    b.i[0, 0] += 1
    assert not np.array_equal(a, b)


def test_array_equal_over_lists_of_tensorobs():
    """The vec-env equivalence test compares LISTS of per-env final_obs
    entries this way -- pin that the list case doesn't raise or silently
    always agree."""
    a = [make(seed=i) for i in range(3)]
    b = [TensorObs(t.f.copy(), t.i.copy()) for t in a]
    assert np.array_equal(a, b)
    b[1].f[0, 0] += 5.0
    assert not np.array_equal(a, b)


def test_array_equal_does_not_raise_the_ambiguous_truth_value_error():
    """The bug this whole design avoids: comparing two PLAIN dicts of
    multi-element arrays via np.array_equal raises ValueError (dict
    equality forces each value comparison to a bare bool). TensorObs must
    not have that failure mode."""
    a, b = make(), make()
    try:
        np.array_equal(a, b)
    except ValueError as e:
        pytest.fail(f"np.array_equal raised on TensorObs: {e}")
