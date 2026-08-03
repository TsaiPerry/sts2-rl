"""Tests for sts2_rl.action_heads.PairPointerHead (phase 2 pointer head) and
PointerHead/FloatPointerHead (R8: pointer scoring for content-carrying run
decisions)."""
import torch

from sts2_rl.action_heads import FloatPointerHead, PairPointerHead, PointerHead

B, S, T = 2, 3, 4
DS, DT, DC, DP = 5, 6, 7, 8


def _head(pair_dim=0):
    torch.manual_seed(0)
    return PairPointerHead(src_dim=DS, tgt_dim=DT, ctx_dim=DC, pair_dim=pair_dim)


def _inputs(pair_dim=0, batch=(B,)):
    torch.manual_seed(1)
    src = torch.randn(*batch, S, DS)
    tgt = torch.randn(*batch, T, DT)
    ctx = torch.randn(*batch, DC)
    pair = torch.randn(*batch, S, T, pair_dim) if pair_dim else None
    return src, tgt, ctx, pair


def test_output_shape_and_row_major_order():
    head = _head()
    src, tgt, ctx, _ = _inputs()
    out = head(src, tgt, ctx)
    assert out.shape == (B, S * T)

    s, t = 1, 2
    single = head(src[:, s:s + 1], tgt[:, t:t + 1], ctx)
    assert single.shape == (B, 1)
    assert torch.allclose(single[:, 0], out[:, s * T + t], atol=1e-6)


def test_source_permutation_equivariance():
    head = _head()
    src, tgt, ctx, _ = _inputs()
    out = head(src, tgt, ctx).view(B, S, T)

    perm = torch.tensor([2, 0, 1])
    out_perm = head(src[:, perm], tgt, ctx).view(B, S, T)

    assert torch.allclose(out_perm, out[:, perm], atol=1e-6)


def test_target_permutation_equivariance():
    head = _head()
    src, tgt, ctx, _ = _inputs()
    out = head(src, tgt, ctx).view(B, S, T)

    perm = torch.tensor([3, 1, 0, 2])
    out_perm = head(src, tgt[:, perm], ctx).view(B, S, T)

    assert torch.allclose(out_perm, out[:, :, perm], atol=1e-6)


def test_pair_features_change_scores():
    head = _head(pair_dim=DP)
    src, tgt, ctx, _ = _inputs()
    zeros = torch.zeros(B, S, T, DP)
    randn = torch.randn(B, S, T, DP)

    out_zeros = head(src, tgt, ctx, pair=zeros)
    out_randn = head(src, tgt, ctx, pair=randn)

    assert not torch.allclose(out_zeros, out_randn)


def test_gradients_reach_all_inputs():
    head = _head(pair_dim=DP)
    src, tgt, ctx, pair = _inputs(pair_dim=DP)
    src.requires_grad_(True)
    tgt.requires_grad_(True)
    ctx.requires_grad_(True)
    pair.requires_grad_(True)

    out = head(src, tgt, ctx, pair=pair)
    out.sum().backward()

    for name, t in [("src", src), ("tgt", tgt), ("ctx", ctx), ("pair", pair)]:
        assert t.grad is not None, f"{name} has no grad"
        assert torch.any(t.grad != 0), f"{name} grad is all zero"


def test_batchless_and_extra_batch_dims():
    head = _head()

    src, tgt, ctx, _ = _inputs(batch=())
    out = head(src, tgt, ctx)
    assert out.shape == (S * T,)

    B1, B2 = 2, 3
    src, tgt, ctx, _ = _inputs(batch=(B1, B2))
    out = head(src, tgt, ctx)
    assert out.shape == (B1, B2, S * T)


def test_batchless_and_extra_batch_dims_with_pair_features():
    """R9 (`sts2_rl.models`'s play-head pair-feature wiring): closes a
    wave-1 review Minor -- `pair` was only ever exercised at the default
    single-batch-dim shape (`test_pair_features_change_scores`,
    `test_gradients_reach_all_inputs`) before this task; nothing proved
    `PairPointerHead(pair=...)` also works batchless (a lone, un-batched
    obs, as `EntitySetActorCritic.action_logits` can receive) or with a
    2-level batch (e.g. a vectorized-env rollout buffer's
    ``(n_envs, n_steps, ...)`` shape)."""
    head = _head(pair_dim=DP)

    src, tgt, ctx, pair = _inputs(pair_dim=DP, batch=())
    out = head(src, tgt, ctx, pair=pair)
    assert out.shape == (S * T,)

    B1, B2 = 2, 3
    src, tgt, ctx, pair = _inputs(pair_dim=DP, batch=(B1, B2))
    out = head(src, tgt, ctx, pair=pair)
    assert out.shape == (B1, B2, S * T)

    # Pair features must actually be READ at both shapes, not silently
    # dropped by a broadcast/expand mismatch that happens to still produce
    # the right output SHAPE -- same liveness check as
    # `test_pair_features_change_scores`, at each batch rank.
    src0, tgt0, ctx0, pair0 = _inputs(pair_dim=DP, batch=())
    out_live = head(src0, tgt0, ctx0, pair=pair0)
    out_dead = head(src0, tgt0, ctx0, pair=torch.zeros_like(pair0))
    assert not torch.allclose(out_live, out_dead)

    src2, tgt2, ctx2, pair2 = _inputs(pair_dim=DP, batch=(B1, B2))
    out_live2 = head(src2, tgt2, ctx2, pair=pair2)
    out_dead2 = head(src2, tgt2, ctx2, pair=torch.zeros_like(pair2))
    assert not torch.allclose(out_live2, out_dead2)


# ── PointerHead / FloatPointerHead (R8: pointer scoring for content-
#    carrying run decisions) ──────────────────────────────────────────────

_N, _D, _DC = 4, 6, 7


def _pointer_head(row_dim=_D, ctx_dim=_DC):
    torch.manual_seed(2)
    return PointerHead(row_dim=row_dim, ctx_dim=ctx_dim)


def _pointer_inputs(row_dim=_D, ctx_dim=_DC, n=_N, batch=(3,)):
    torch.manual_seed(3)
    rows = torch.randn(*batch, n, row_dim)
    ctx = torch.randn(*batch, ctx_dim)
    return rows, ctx


def _force_nonzero_bias(module: torch.nn.Module, value: float = 0.37) -> None:
    """`_layer_init` zeroes every Linear's bias, so at a fresh init
    `f(0) == 0` already, independent of presence gating -- that would let a
    mutant that drops the `* present` multiply pass the gating test by
    accident. Force every Linear bias nonzero first, mirroring
    `test_entset_rows.py::test_pad_rows_are_zero_vectors`'s own fixture."""
    with torch.no_grad():
        for m in module.modules():
            if isinstance(m, torch.nn.Linear):
                m.bias.fill_(value)


def test_pointer_head_output_shape():
    head = _pointer_head()
    rows, ctx = _pointer_inputs()
    out = head(rows, ctx)
    assert out.shape == (3, _N)


def test_pointer_head_row_permutation_equivariance():
    head = _pointer_head()
    rows, ctx = _pointer_inputs()
    out = head(rows, ctx)

    perm = torch.tensor([2, 0, 3, 1])
    out_perm = head(rows[:, perm], ctx)
    assert torch.allclose(out_perm, out[:, perm], atol=1e-6)


def test_pointer_head_presence_gating_zero_row_scores_exactly_zero():
    head = _pointer_head()
    _force_nonzero_bias(head)
    rows, ctx = _pointer_inputs()
    rows = rows.clone()
    rows[:, 1, :] = 0.0   # PAD row, as the entset encoder guarantees

    out = head(rows, ctx)
    assert torch.equal(out[:, 1], torch.zeros(3))
    # Sanity: a genuinely present row (nonzero bias forced above) is NOT
    # all-zero, so the zero at index 1 is the gate, not universal collapse.
    assert not torch.equal(out[:, 0], torch.zeros(3))


def test_pointer_head_gradients_reach_all_inputs():
    head = _pointer_head()
    rows, ctx = _pointer_inputs()
    rows.requires_grad_(True)
    ctx.requires_grad_(True)

    out = head(rows, ctx)
    out.sum().backward()

    assert rows.grad is not None and torch.any(rows.grad != 0)
    assert ctx.grad is not None and torch.any(ctx.grad != 0)


_W = 3   # e.g. a map{k} slot's (present, type-onehot...) width


def _float_pointer_head(seg_dim=_W, ctx_dim=_DC):
    torch.manual_seed(4)
    return FloatPointerHead(seg_dim=seg_dim, ctx_dim=ctx_dim)


def _float_pointer_inputs(seg_dim=_W, ctx_dim=_DC, n=_N, batch=(3,)):
    torch.manual_seed(5)
    seg = torch.randn(*batch, n, seg_dim)
    ctx = torch.randn(*batch, ctx_dim)
    return seg, ctx


def test_float_pointer_head_output_shape():
    head = _float_pointer_head()
    seg, ctx = _float_pointer_inputs()
    out = head(seg, ctx)
    assert out.shape == (3, _N)


def test_float_pointer_head_segment_permutation_equivariance():
    head = _float_pointer_head()
    seg, ctx = _float_pointer_inputs()
    out = head(seg, ctx)

    perm = torch.tensor([3, 1, 0, 2])
    out_perm = head(seg[:, perm], ctx)
    assert torch.allclose(out_perm, out[:, perm], atol=1e-6)


def test_float_pointer_head_presence_gating_zero_segment_scores_exactly_zero():
    head = _float_pointer_head()
    _force_nonzero_bias(head)
    seg, ctx = _float_pointer_inputs()
    seg = seg.clone()
    seg[:, 2, :] = 0.0   # absent slot (e.g. a MAP option beyond len(points))

    out = head(seg, ctx)
    assert torch.equal(out[:, 2], torch.zeros(3))
    assert not torch.equal(out[:, 0], torch.zeros(3))


def test_float_pointer_head_gradients_reach_all_inputs():
    head = _float_pointer_head()
    seg, ctx = _float_pointer_inputs()
    seg.requires_grad_(True)
    ctx.requires_grad_(True)

    out = head(seg, ctx)
    out.sum().backward()

    assert seg.grad is not None and torch.any(seg.grad != 0)
    assert ctx.grad is not None and torch.any(ctx.grad != 0)
