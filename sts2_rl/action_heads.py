"""Pointer-style action heads for the entset architecture (phase 2)."""
import torch
from torch import Tensor, nn

from .models import _layer_init


class PairPointerHead(nn.Module):
    """Scores every (source_row, target_row) pair, row-major (src*T + tgt),
    matching decode_combat_action's h*MAX_ENEMIES + e ordering.

    src rows and tgt rows are the mask-multiplied per-row features the
    entset encoder produces (PAD row == zero vector); ctx is the actor
    trunk's feature vector; pair is an optional (..., S, T, pair_dim)
    tensor of per-pair features (R9).
    """

    def __init__(self, src_dim: int, tgt_dim: int, ctx_dim: int,
                 pair_dim: int = 0, hidden: int = 64) -> None:
        super().__init__()
        self.ctx_proj = _layer_init(nn.Linear(ctx_dim, 32))
        self.mlp = nn.Sequential(
            _layer_init(nn.Linear(src_dim + tgt_dim + 32 + pair_dim, hidden)),
            nn.Tanh(),
            _layer_init(nn.Linear(hidden, 1), std=0.01),
        )

    def forward(self, src: Tensor, tgt: Tensor, ctx: Tensor,
                pair: Tensor | None = None) -> Tensor:
        # src (..., S, ds); tgt (..., T, dt); ctx (..., dc) -> (..., S*T)
        S, T = src.shape[-2], tgt.shape[-2]
        s = src.unsqueeze(-2).expand(*src.shape[:-2], S, T, src.shape[-1])
        t = tgt.unsqueeze(-3).expand(*tgt.shape[:-2], S, T, tgt.shape[-1])
        c = torch.tanh(self.ctx_proj(ctx)).unsqueeze(-2).unsqueeze(-2) \
            .expand(*ctx.shape[:-1], S, T, 32)
        parts = [s, t, c] + ([pair] if pair is not None else [])
        return self.mlp(torch.cat(parts, dim=-1)).squeeze(-1).flatten(-2)


class PointerHead(nn.Module):
    """Scores each row of one entity set against the context (R8 brief:
    content-carrying run decisions -- SELECT-by-candidate, the belt-POTION
    block, and the per-mechanism overlays onto CHOICE).

    Presence-gated: a PAD row (exact zero vector, as the entset encoder
    guarantees -- ``_EntsetEncoder.encode``'s ``rows`` dict) contributes
    EXACTLY 0.0, not ``f(0) = bias`` -- so an out-of-phase block (e.g.
    ``reward.cards`` on a SHOP obs) is inert in an additive slot score by
    construction, not merely "usually small".
    """

    def __init__(self, row_dim: int, ctx_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.ctx_proj = _layer_init(nn.Linear(ctx_dim, 32))
        self.mlp = nn.Sequential(
            _layer_init(nn.Linear(row_dim + 32, hidden)), nn.Tanh(),
            _layer_init(nn.Linear(hidden, 1), std=0.01),
        )

    def forward(self, rows: Tensor, ctx: Tensor) -> Tensor:
        # rows (..., N, d); ctx (..., dc) -> (..., N)
        N = rows.shape[-2]
        c = torch.tanh(self.ctx_proj(ctx)).unsqueeze(-2).expand(
            *ctx.shape[:-1], N, 32)
        scores = self.mlp(torch.cat([rows, c], dim=-1)).squeeze(-1)
        present = (rows != 0).any(dim=-1).to(scores.dtype)
        return scores * present


class FloatPointerHead(nn.Module):
    """Like :class:`PointerHead`, but scores a raw FLOAT segment (a
    ``.f``-only obs segment with no paired entity-row block, e.g. one
    ``map{k}`` slot's floats or the ``shop.removal`` triple) instead of an
    encoder row -- the ``choice_float_overlays`` mechanism (R8 brief).

    A shared ``seg_dim -> 32`` projection (``Linear`` + ``tanh``) turns the
    raw segment into a row-shaped feature before the same scored-and-gated
    MLP pattern ``PointerHead`` uses. Presence is gated on the RAW segment
    being not-all-zero -- checked BEFORE the projection, because a nonzero
    bias in ``seg_proj`` would otherwise turn an all-zero (absent/PAD)
    segment into a nonzero projected row and defeat the gate.
    """

    def __init__(self, seg_dim: int, ctx_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.seg_proj = _layer_init(nn.Linear(seg_dim, 32))
        self.ctx_proj = _layer_init(nn.Linear(ctx_dim, 32))
        self.mlp = nn.Sequential(
            _layer_init(nn.Linear(64, hidden)), nn.Tanh(),
            _layer_init(nn.Linear(hidden, 1), std=0.01),
        )

    def forward(self, seg: Tensor, ctx: Tensor) -> Tensor:
        # seg (..., N, w); ctx (..., dc) -> (..., N)
        N = seg.shape[-2]
        present = (seg != 0).any(dim=-1).to(seg.dtype)
        s = torch.tanh(self.seg_proj(seg))
        c = torch.tanh(self.ctx_proj(ctx)).unsqueeze(-2).expand(
            *ctx.shape[:-1], N, 32)
        scores = self.mlp(torch.cat([s, c], dim=-1)).squeeze(-1)
        return scores * present
