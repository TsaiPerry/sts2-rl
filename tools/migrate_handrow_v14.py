"""One-shot lossless migration: run-scale entset checkpoint, obs schema
11 -> 12 (hand.f 29 -> 31 floats/row, v14 glow_gold + block_preview_move).

Concat order (confirmed against `_EntsetEncoder.encode` in sts2_rl/models.py,
2026-08: the per-row tensor is built as
``row = torch.cat(pieces, dim=-1)`` where ``pieces`` is every int field's
embedding/literal IN VOCAB ORDER, followed by ``floats`` appended LAST when
the block has any (``if meta["n_float"]: pieces.append(floats)``). So floats
are the TAIL of each row, and the two new v14 floats (f[29]/f[30]) are
themselves the tail of the (now 31-wide) float block -- they insert at the
very END of the row, i.e. at column ``row_in_old`` (the old row's full
width), not at some interior offset.

The hand row-projection ``Linear`` therefore gains 2 zero input columns
appended at the end of its weight's input dimension. Zero columns mean the
two new inputs are multiplied by 0 and contribute nothing to the projection,
so the migrated policy's outputs are bit-identical to the source
checkpoint's (proven by test_migrate_handrow_v14.py's
``test_migrated_model_ignores_new_fields``, which randomizes f[29]/f[30] and
asserts unchanged logits). Adam moments are spliced identically at the same
position (positional `optim.state`, param order unchanged by this
migration).

Discovered key (Step 5, against runs/sts2_run_torch_v13_s15.pt): the
checkpoint has `shared_encoder: True`, meaning the actor and critic share
ONE `_EntsetEncoder` instance (`EntitySetActorCritic.__init__` registers it
under `actor_encoder` only, via `object.__setattr__` for the `critic_encoder`
alias so it is never double-registered in `state_dict()`/
`named_parameters()`) -- confirmed by the checkpoint's `model` dict having
zero `critic_encoder.*` keys. So there is exactly ONE weight to splice:
`actor_encoder._blocks.15.weight` -- index 15 is `combat.hand.ids`'s
position in the run-scale layout's row-block order (see
`entset_segment_plan` over `model_obs_layout(ModelSpec("run", arch="entset"))`
-- confirmed by listing block shapes against the real checkpoint: block 15
is (32, 73), and 73 = row_in_old (44 embed dims + 29 old floats), matching
the schema-12 code's fresh block 15 shape (32, 75) minus 2.
"""
import argparse
import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

def _hand_block_index() -> int:
    """Position of ``combat.hand.ids``'s row block in the CURRENT run-scale
    layout.

    Derived, not hardcoded: this was the literal 15 quoted in the module
    docstring, and adding ``event.options.cards.ids`` to the run int segments
    (schema 13) shifted every combat block one place right. A stale literal
    here does not fail loudly -- it splices zero columns into whatever block
    now sits at that index, quietly corrupting an unrelated projection.
    """
    from sts2_rl import models
    from sts2_rl.checkpoints import ModelSpec, model_obs_layout

    spec = ModelSpec("run", arch="entset")
    f_segs, i_segs = model_obs_layout(spec)
    row_blocks, _raw_f = models.entset_segment_plan(f_segs, i_segs)
    for idx, (name, *_rest) in enumerate(row_blocks):
        if models._entset_logical_name(name) == "hand":
            return idx
    raise RuntimeError("no 'hand' row block in the run-scale layout")


#: The hand row-projection weight key(s) to splice. shared_encoder=True in
#: the real checkpoint means only the actor-side encoder is registered in
#: state_dict (see module docstring) -- one key, not an actor/critic pair.
HAND_PROJECTION_KEYS = (f"actor_encoder._blocks.{_hand_block_index()}.weight",)

#: Floats are the tail of the row (module docstring); the splice position is
#: the OLD row's full width, discovered per-checkpoint from that weight's own
#: shape (so this tool needs no hardcoded row-width constant).
NEW_FLOAT_WIDTH = 2


def splice_zero_columns(mat: torch.Tensor, insert_at: int, width: int) -> torch.Tensor:
    return torch.cat(
        [mat[:, :insert_at], mat.new_zeros(mat.shape[0], width), mat[:, insert_at:]],
        dim=1)


def migrate(src, dst) -> None:
    ck = torch.load(src, map_location="cpu", weights_only=False)
    if ck.get("obs_schema") != 11:
        sys.exit(f"expected obs_schema 11, got {ck.get('obs_schema')}")
    if ck.get("arch") != "entset" or ck.get("env_kind") != "run":
        sys.exit("this tool migrates run-scale entset checkpoints only")
    if not ck.get("shared_encoder", False):
        sys.exit(
            "this tool's hardcoded HAND_PROJECTION_KEYS assumes "
            "shared_encoder=True (one actor_encoder, no separate "
            "critic_encoder keys); this checkpoint has shared_encoder="
            f"{ck.get('shared_encoder')!r} -- extend HAND_PROJECTION_KEYS "
            "with the critic-side key before migrating it.")

    model = ck["model"]
    from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout

    spec = ModelSpec(
        env_kind="run", arch="entset", hidden=tuple(ck.get("hidden", (256, 256))),
        shared_encoder=True)
    # NOT ck["obs_dim"] -- that stamp is the SOURCE (schema-11) width, and
    # make_model refuses a mismatch against the CURRENT (schema-12) segment
    # layout. Only parameter NAMES are needed here (unchanged by this
    # migration), so build against today's real layout width instead.
    f_segments, i_segments = model_obs_layout(spec)
    f_dim = sum(w for _, w in f_segments)
    i_dim = sum(w for _, w in i_segments)
    agent = make_model(spec, (f_dim, i_dim), ck["n_actions"])
    param_names = [n for n, _ in agent.named_parameters()]

    for key in HAND_PROJECTION_KEYS:
        w = model[key]
        insert_at = w.shape[1]
        model[key] = splice_zero_columns(w, insert_at=insert_at, width=NEW_FLOAT_WIDTH)
        pstate = ck.get("optim", {}).get("state", {}).get(param_names.index(key))
        if pstate is not None:
            for moment in ("exp_avg", "exp_avg_sq"):
                if moment in pstate:
                    pstate[moment] = splice_zero_columns(
                        pstate[moment], insert_at=insert_at, width=NEW_FLOAT_WIDTH)
    # `check_checkpoint` (checkpoints.py) hard-refuses on `obs_dim` mismatch
    # against the live env's measured width -- the stale schema-11 (f=4715)
    # stamp must move to schema-12's (f=4735) alongside the weight splice,
    # or eval.py's load would reject this checkpoint outright.
    ck["obs_dim"] = (f_dim, i_dim)
    ck["obs_schema"] = 12
    torch.save(ck, dst)
    print(f"migrated {src} -> {dst} (obs_schema 12, keys: {list(HAND_PROJECTION_KEYS)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    migrate(a.src, a.dst)
