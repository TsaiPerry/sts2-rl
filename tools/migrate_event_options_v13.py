"""Migrate a run-scale entset checkpoint from obs schema 12 to 13.

Schema 13 adds four int blocks to the run observation — the content each event
option previews:

    event.options.cards.ids
    event.options.relics.ids
    event.options.relics_traded.ids
    event.options.potions.ids

They land CONTIGUOUSLY in the encoder's row-block order (right after ``event``),
which is what makes this migration mechanical. Two consequences, and both must
be handled or the migrated weights are silently wrong:

1. ``_EntsetEncoder._blocks`` is a positionally indexed ``ModuleList``, so every
   block at or after the insertion point shifts. A checkpoint's
   ``_blocks.k`` must be renumbered, NOT loaded by name — several blocks share a
   shape (the six ``enemy*.powers`` projections are all ``(32, 36)``), so a
   stale index loads a shape-compatible but WRONG projection and nothing raises.
   This is exactly what ``warm_start_agent`` does if pointed at a v12
   checkpoint: measured 129/149 keys "transferred", with ``enemy2.powers``
   receiving ``enemy3.powers``'s weights. Do not use it for this.

2. The encoder's pooled output widens by ``block_dim`` per new block, so the
   first trunk ``Linear``s (``actor.0`` / ``critic.0``) gain input columns. We
   splice ZERO columns at the new blocks' pooled positions, so the new inputs
   contribute exactly nothing until training moves those weights: the migrated
   model is numerically identical to the source on every observation, and then
   learns to use the new signal. Same technique as
   ``tools/migrate_handrow_v14.py``'s row splice.

Adam's ``exp_avg``/``exp_avg_sq`` are keyed by PARAMETER POSITION, so they get
the identical renumber-and-splice treatment; skipping that would pair a
parameter with another parameter's moments.

Usage:
    python tools/migrate_event_options_v13.py OLD.pt NEW.pt
"""
import argparse
import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

#: Logical block names introduced by schema 13. Everything else in the v13
#: layout is assumed to exist in v12, in the same relative order.
NEW_LOGICAL_BLOCKS = (
    "event.options.cards",
    "event.options.relics",
    "event.options.relics_traded",
    "event.options.potions",
)

OLD_SCHEMA = 12
NEW_SCHEMA = 13


def _plan(spec):
    from sts2_rl import models
    from sts2_rl.checkpoints import model_obs_layout

    f_segs, i_segs = model_obs_layout(spec)
    row_blocks, _raw_f = models.entset_segment_plan(f_segs, i_segs)
    return [models._entset_logical_name(name) for name, *_rest in row_blocks]


def block_index_map(logical_names: list[str]) -> tuple[dict[int, int], list[int]]:
    """``{old_block_index: new_block_index}`` plus the new indices with no
    source. Built by walking the NEW order and handing out old indices to every
    block that is not new — so it stays correct if a later schema inserts
    elsewhere, instead of assuming a contiguous run."""
    mapping: dict[int, int] = {}
    fresh: list[int] = []
    old_idx = 0
    for new_idx, name in enumerate(logical_names):
        if name in NEW_LOGICAL_BLOCKS:
            fresh.append(new_idx)
        else:
            mapping[old_idx] = new_idx
            old_idx += 1
    return mapping, fresh


def splice_zero_columns(mat: torch.Tensor, insert_at: int, width: int) -> torch.Tensor:
    """Insert ``width`` zero columns into ``mat`` at column ``insert_at``."""
    left, right = mat[:, :insert_at], mat[:, insert_at:]
    zeros = torch.zeros(mat.shape[0], width, dtype=mat.dtype, device=mat.device)
    return torch.cat([left, zeros, right], dim=1)


def _splice_spans(mat: torch.Tensor, fresh: list[int], block_dim: int) -> torch.Tensor:
    """Splice one zero span per new block, RIGHT TO LEFT so each insertion
    position stays valid in the original coordinate system."""
    for new_idx in sorted(fresh, reverse=True):
        mat = splice_zero_columns(mat, new_idx * block_dim, block_dim)
    return mat


def migrate(old_path: Path, new_path: Path) -> dict:
    from sts2_rl import run_env
    from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout

    ckpt = torch.load(old_path, map_location="cpu", weights_only=False)

    schema = ckpt.get("obs_schema")
    if schema != OLD_SCHEMA:
        raise SystemExit(
            f"{old_path} has obs_schema {schema!r}, expected {OLD_SCHEMA}. This "
            f"tool migrates {OLD_SCHEMA} -> {NEW_SCHEMA} only.")
    if ckpt.get("arch") != "entset" or ckpt.get("env_kind") not in ("run", "column"):
        raise SystemExit(
            f"{old_path} is arch={ckpt.get('arch')!r} env_kind={ckpt.get('env_kind')!r}; "
            f"this migration is for run-scale entset checkpoints.")

    spec = ModelSpec(ckpt["env_kind"], arch="entset", hidden=tuple(ckpt["hidden"]),
                     shared_encoder=ckpt.get("shared_encoder", False))
    names = _plan(spec)
    mapping, fresh = block_index_map(names)

    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    target = make_model(spec, obs_dim, run_env.N_ACTIONS)
    target_sd = target.state_dict()

    old_model = ckpt["model"]
    # block_dim is the row projections' OUT width, read off the target rather
    # than assumed, so a changed encoder width cannot silently mis-splice.
    block_dim = target_sd[f"actor_encoder._blocks.{fresh[0]}.weight"].shape[0]

    out: dict[str, torch.Tensor] = {}
    renumbered = 0
    for key, value in old_model.items():
        if "._blocks." in key:
            prefix, rest = key.split("._blocks.", 1)
            idx_str, suffix = rest.split(".", 1)
            new_idx = mapping[int(idx_str)]
            out[f"{prefix}._blocks.{new_idx}.{suffix}"] = value
            renumbered += 1
        else:
            out[key] = value

    # The new blocks' projections are ZEROED, not fresh-random. A zero Linear
    # emits an all-zero row embedding whatever the new ids are, so EVERY
    # downstream consumer sees exactly nothing -- the pooled trunk, the aux
    # heads, and the per-row pointer/overlay heads alike. Zero-splicing the
    # pooled consumers alone was not enough (measured: logits still moved),
    # because a row block feeds more than the pooled vector, and enumerating
    # its readers is precisely the fragile thing this avoids.
    #
    # Zero weights still TRAIN: dL/dW = dL/dout . input^T is non-zero, so the
    # block starts contributing as soon as the first update lands. This is the
    # standard zero-init-a-new-branch trick, not a dead branch.
    for new_idx in fresh:
        for suffix in ("weight", "bias"):
            for prefix in ("actor_encoder", "critic_encoder"):
                key = f"{prefix}._blocks.{new_idx}.{suffix}"
                if key in target_sd:
                    out[key] = torch.zeros_like(target_sd[key])

    # Every layer that consumes the POOLED encoder output widens by
    # len(fresh) * block_dim. Found by shape rather than by name: the trunk's
    # actor.0/critic.0 are the obvious two, but the auxiliary prediction heads
    # (aux_hp3_head and friends) read the same vector, and a hardcoded key list
    # silently misses whichever head is added next — the migration then fails
    # loudly at load time, or worse, quietly if the shapes happen to line up.
    new_pooled = target_sd["actor.0.weight"].shape[1]
    old_pooled = new_pooled - len(fresh) * block_dim
    spliced = []
    for key, value in list(out.items()):
        if (value.ndim == 2 and value.shape[1] == old_pooled
                and key in target_sd and target_sd[key].shape[1] == new_pooled):
            out[key] = _splice_spans(value, fresh, block_dim)
            spliced.append(key)

    mismatched = [k for k in out
                  if k in target_sd and out[k].shape != target_sd[k].shape]
    if mismatched:
        raise SystemExit(
            f"shape mismatch after migration for {mismatched} — the block "
            f"layout is not what this tool assumes.")

    # Adam moments are positional: same renumber, same splice.
    optim = ckpt.get("optim")
    if optim is not None and "state" in optim:
        param_names = [n for n, _ in target.named_parameters()]
        new_state = {}
        old_param_names = [n for n in param_names
                           if not any(f"._blocks.{i}." in n for i in fresh)]
        for old_pos, moments in optim["state"].items():
            name = old_param_names[int(old_pos)]
            new_pos = param_names.index(name)
            m = dict(moments)
            if name in spliced:
                for moment in ("exp_avg", "exp_avg_sq"):
                    if moment in m:
                        m[moment] = _splice_spans(m[moment], fresh, block_dim)
            new_state[new_pos] = m
        # Fresh params start with no moment state at all — Adam initialises
        # lazily on their first step, which is what a fresh param should get.
        optim["state"] = new_state
        if optim.get("param_groups"):
            optim["param_groups"][0]["params"] = list(range(len(param_names)))

    ckpt["model"] = out
    ckpt["obs_schema"] = NEW_SCHEMA
    ckpt["obs_dim"] = obs_dim
    torch.save(ckpt, new_path)

    print(f"migrated {old_path} -> {new_path}\n"
          f"  obs_schema {OLD_SCHEMA} -> {NEW_SCHEMA}, obs_dim -> {obs_dim}\n"
          f"  renumbered {renumbered} block tensors, "
          f"fresh blocks at {fresh}, spliced {len(fresh) * block_dim} "
          f"zero columns into {', '.join(spliced)}")
    return ckpt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    args = ap.parse_args()
    migrate(args.old, args.new)


if __name__ == "__main__":
    main()
