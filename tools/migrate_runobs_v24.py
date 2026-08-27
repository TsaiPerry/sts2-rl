"""Migrate a run-scale entset checkpoint from obs schema 12 to 13.

Schema 13's full delta (v24 ascension-fold plan, Tasks 1-2) has TWO
independent parts, discovered against the real seed checkpoint via
``tools/dump_layout_keys_v24.py runs/sts2_run_torch_v23_s26.pt`` (output
saved to the task-3 scratchpad):

1. FOUR new row blocks -- ``event.options.{cards,relics,relics_traded,
   potions}.ids`` -- landing CONTIGUOUSLY right after ``event.ids`` in the
   row-block order (new indices 5-8 in the live 29-row-block plan; the old
   schema-12 layout had 25 row blocks, 0-24, with ``shop.cards.ids`` etc.
   shifting from old index 5 to new index 9). This is exactly
   ``tools/migrate_event_options_v13.py``'s job, and its machinery
   (``block_index_map``, ``splice_zero_columns``) is reused verbatim here
   rather than duplicated.

2. ONE new raw (non-row-block) float, ``run.ascension`` -- NOT at the tail
   of the encoder's pooled output as the naive "last f segment" reading of
   ``run_env.py`` might suggest. Row blocks are pooled and concatenated
   FIRST, then raw float segments are appended in ``f_segments`` layout
   order (``_EntsetEncoder.__init__``); ``run.ascension`` is declared in
   ``run_obs_segments_f`` right after ``select.candidates.overflow`` and
   BEFORE any ``combat.*`` segment, so in the pooled encoder-out vector it
   sits mid-stream, immediately after the 4 new event-option blocks'
   contribution and before ~30 columns of existing combat raw floats.
   Confirmed by ``dump_layout_keys_v24.py`` against the live layout: 29 row
   blocks (indices 0-28) at block_dim=32 each, then raw floats in this
   order: phase, run.hp_ratio, ..., select.candidates.overflow,
   **run.ascension** (width 1), combat.player.hp_ratio, ... -- i.e.
   ``run.ascension`` is the LAST raw float BEFORE the combat.* raw floats,
   not the last raw float overall.

Both deltas widen the trunk's first ``Linear``s (``actor.0``/``critic.0``,
and any other layer reading the pooled vector, e.g. ``aux_hp3_head.0`` --
found generically by shape, not by a hardcoded key list, same as v13) by
the same total: ``4 * block_dim + 1``. We splice ZERO columns at both the
4 block positions AND the 1 ascension position (five separate insertions,
applied right-to-left in one pass so each insertion point stays valid in
source coordinates) -- discovered against the real seed checkpoint:
``actor.0.weight`` / ``critic.0.weight`` / ``aux_hp3_head.0.weight`` all go
from input width 3253 (source) to 3382 (live target) = +128 (4*32) +1.
Zero columns make the new inputs (four fresh embedding blocks AND the raw
ascension float) contribute exactly nothing until training moves those
weights, so the migrated model's outputs are bit-identical to the source
checkpoint's: both on any schema-13 observation whatever it puts in the new
fields (new-field inertness), AND on the source checkpoint's own old fields
carried straight across into their new positions (old-field preservation --
the renumbering/splicing did not scramble anything). Both are proven by
test/test_migrate_v24.py against the real seed checkpoint.

Adam's ``exp_avg``/``exp_avg_sq`` are keyed by PARAMETER POSITION and get
the identical renumber-and-splice treatment (same technique as
``migrate_event_options_v13``/``migrate_handrow_v14``).

Usage:
    python tools/migrate_runobs_v24.py OLD.pt NEW.pt
"""
import argparse
import sys
from pathlib import Path

import torch

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.migrate_event_options_v13 import (
    NEW_LOGICAL_BLOCKS, block_index_map, splice_zero_columns, _plan)

OLD_SCHEMA = 12
NEW_SCHEMA = 13

#: The one new raw (non-row-block) float segment schema 13 adds, keyed by
#: its ``_EntsetEncoder.out_spans`` name (no width literal here -- read off
#: the live target's own ``out_spans`` at migration time, same discipline
#: as v13's block_dim).
NEW_RAW_F_SEGMENT = "run.ascension"


def old_new_layouts(spec) -> tuple[list, list, list, list]:
    """``(old_f_segs, old_i_segs, new_f_segs, new_i_segs)`` -- the schema-12
    and live (schema-13) obs segment lists, by NAME, for building a
    schema-12-shaped obs and a schema-13-shaped obs that carry the SAME
    values in every shared segment (only the segment lists differ, not any
    within-segment width). Exposed for ``test/test_migrate_v24.py``'s
    source-vs-migrated bit-identical check, so it maps old obs fields to
    their new positions the same way this tool does, instead of
    reimplementing the offset arithmetic.

    ``model_obs_layout`` only ever returns the CURRENT (live) layout, so the
    schema-12 lists are derived by filtering the two new-in-13 pieces back
    out, in place, preserving every other segment's relative order --
    exactly the assumption ``block_index_map`` already makes for row
    blocks (see migrate_event_options_v13.block_index_map's docstring).
    """
    from sts2_rl.checkpoints import model_obs_layout

    f_segs, i_segs = model_obs_layout(spec)
    old_f_segs = [(n, w) for n, w in f_segs if n != NEW_RAW_F_SEGMENT]
    fresh_i_names = {f"{n}.ids" for n in NEW_LOGICAL_BLOCKS}
    old_i_segs = [(n, w) for n, w in i_segs if n not in fresh_i_names]
    return old_f_segs, old_i_segs, f_segs, i_segs


def _merge_adjacent_specs(specs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Coalesce ``(position, width)`` entries that are CONTIGUOUS in the
    original (pre-splice) coordinate system into one combined span.

    This matters because inserting several specs independently, each at its
    own OLD-coordinate position, is only correct when every position is a
    genuine distinct junction in the ORIGINAL matrix (old content on both
    sides). Two specs whose positions are adjacent (``pos2 == pos1 +
    width1``) share a junction -- there is no old content between them, so
    treating them as independent insertions scatters what should be one
    contiguous new-content span: inserting at ``pos1`` first shifts
    everything at or after ``pos1`` (including the intended ``pos2``) right
    by ``width1``, so the second insertion lands ``width1`` columns too far
    right of where the (still un-shifted) ``pos2`` coordinate meant it to.
    Concretely, for this tool's 4 contiguous fresh row blocks at old
    positions 160/192/224/256 (block_dim=32 each), un-merged specs produce
    zero spans at final positions 160-192, 224-256, 288-320, 352-384 --
    scattered, with genuine (wrong!) old content interleaved between them
    -- instead of one contiguous 160-288 zero region. Caught by
    test/test_migrate_v24.py's source-vs-migrated comparison (bit-identical
    old-field logits), which a self-consistency-only test (new fields
    randomized vs zeroed on the SAME migrated model) cannot catch: the scatter
    still leaves the new fields' own columns zero-weighted, so that check
    alone passes even with this bug.
    """
    merged: list[tuple[int, int]] = []
    for pos, width in sorted(specs, key=lambda p: p[0]):
        if merged and merged[-1][0] + merged[-1][1] == pos:
            prev_pos, prev_width = merged.pop()
            merged.append((prev_pos, prev_width + width))
        else:
            merged.append((pos, width))
    return merged


def _splice_many(mat: torch.Tensor, specs: list[tuple[int, int]]) -> torch.Tensor:
    """Insert one zero span per ``(position, width)`` in ``specs``, after
    merging adjacent entries into contiguous spans (see
    ``_merge_adjacent_specs``), RIGHT TO LEFT (by position, descending) so
    each insertion point stays valid in the original (pre-splice)
    coordinate system."""
    for pos, width in sorted(_merge_adjacent_specs(specs), key=lambda p: p[0], reverse=True):
        mat = splice_zero_columns(mat, pos, width)
    return mat


def migrate(old_path: Path, new_path: Path) -> dict:
    from sts2_rl import run_env
    from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout

    ckpt = torch.load(old_path, map_location="cpu", weights_only=False)

    schema = ckpt.get("obs_schema")
    if schema != OLD_SCHEMA:
        raise SystemExit(
            f"{old_path} has obs_schema {schema!r}, expected {OLD_SCHEMA}. "
            f"This tool migrates {OLD_SCHEMA} -> {NEW_SCHEMA} only.")
    if ckpt.get("arch") != "entset" or ckpt.get("env_kind") != "run":
        raise SystemExit(
            f"{old_path} is arch={ckpt.get('arch')!r} env_kind="
            f"{ckpt.get('env_kind')!r}; this migration is for run-scale "
            f"entset checkpoints only.")
    if not ckpt.get("shared_encoder", False):
        raise SystemExit(
            f"{old_path} has shared_encoder={ckpt.get('shared_encoder')!r}; "
            f"this tool assumes shared_encoder=True (one actor_encoder, no "
            f"separate critic_encoder keys) -- extend it before use on a "
            f"non-shared checkpoint.")

    spec = ModelSpec(ckpt["env_kind"], arch="entset", hidden=tuple(ckpt["hidden"]),
                     shared_encoder=True)
    names = _plan(spec)
    mapping, fresh = block_index_map(names)

    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    target = make_model(spec, obs_dim, run_env.N_ACTIONS)
    target_sd = target.state_dict()

    old_model = ckpt["model"]
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

    # The 4 new blocks' projections are ZEROED (not fresh-random) -- see
    # migrate_event_options_v13's docstring for why: a zero Linear emits an
    # all-zero row embedding whatever the new ids are, so every downstream
    # consumer (pooled trunk, aux heads, pointer/overlay heads) sees exactly
    # nothing. ``run.ascension`` needs no equivalent step: it is a raw float
    # column, not an embedding block -- zeroing the trunk's INPUT column for
    # it (below) is sufficient on its own.
    for new_idx in fresh:
        for suffix in ("weight", "bias"):
            for prefix in ("actor_encoder", "critic_encoder"):
                key = f"{prefix}._blocks.{new_idx}.{suffix}"
                if key in target_sd:
                    out[key] = torch.zeros_like(target_sd[key])

    # Splice positions, in the NEW (live) pooled-vector coordinate system:
    # the 4 fresh row blocks at their block-index * block_dim offsets, plus
    # `run.ascension`'s own out_span (read off the live target encoder, not
    # assumed -- it is NOT the tail column; see module docstring).
    ascension_start, ascension_end = target.actor_encoder.out_spans[NEW_RAW_F_SEGMENT]
    ascension_width = ascension_end - ascension_start
    total_new_width = len(fresh) * block_dim + ascension_width
    # `ascension_start` is read off the LIVE (schema-13) target, so it
    # already sits `len(fresh) * block_dim` columns higher than its true
    # position in the OLD (source) matrix -- every fresh row block precedes
    # every raw float segment in encoder-out order (see module docstring),
    # so all 4 new blocks' width has already been added to any raw-float
    # offset in the new coordinate system. Subtract it back out so this
    # splice position is expressed in OLD coordinates, matching the block
    # positions below (both are then spliced together, right-to-left, over
    # the OLD-width source tensor).
    ascension_pos_old = ascension_start - len(fresh) * block_dim
    splice_specs = [(new_idx * block_dim, block_dim) for new_idx in fresh]
    splice_specs.append((ascension_pos_old, ascension_width))

    new_pooled = target_sd["actor.0.weight"].shape[1]
    old_pooled = new_pooled - total_new_width
    # Sanity-check against the SOURCE checkpoint's own actor.0.weight width,
    # rather than trusting the arithmetic blindly -- a mismatch here means
    # the discovery's assumptions about the delta no longer hold.
    src_pooled = old_model.get("actor.0.weight")
    if src_pooled is not None and src_pooled.shape[1] != old_pooled:
        raise SystemExit(
            f"source actor.0.weight has input width {src_pooled.shape[1]}, "
            f"expected {old_pooled} (= live {new_pooled} - {total_new_width}); "
            f"the discovered delta no longer matches this checkpoint.")

    spliced = []
    for key, value in list(out.items()):
        if (value.ndim == 2 and value.shape[1] == old_pooled
                and key in target_sd and target_sd[key].shape[1] == new_pooled):
            out[key] = _splice_many(value, splice_specs)
            spliced.append(key)

    mismatched = [k for k in out
                  if k in target_sd and out[k].shape != target_sd[k].shape]
    if mismatched:
        raise SystemExit(
            f"shape mismatch after migration for {mismatched} -- the block "
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
                        m[moment] = _splice_many(m[moment], splice_specs)
            new_state[new_pos] = m
        # Fresh params (the 4 zeroed blocks) start with no moment state at
        # all -- Adam initialises lazily on their first step.
        optim["state"] = new_state
        if optim.get("param_groups"):
            optim["param_groups"][0]["params"] = list(range(len(param_names)))

    ckpt["model"] = out
    ckpt["obs_schema"] = NEW_SCHEMA
    ckpt["obs_dim"] = obs_dim
    torch.save(ckpt, new_path)

    print(f"migrated {old_path} -> {new_path}\n"
          f"  obs_schema {OLD_SCHEMA} -> {NEW_SCHEMA}, obs_dim -> {obs_dim}\n"
          f"  renumbered {renumbered} block tensors, fresh blocks at {fresh}, "
          f"ascension splice at column {ascension_start}, "
          f"spliced {total_new_width} zero columns into "
          f"{', '.join(spliced)}")
    return ckpt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    args = ap.parse_args()
    migrate(args.old, args.new)


if __name__ == "__main__":
    main()
