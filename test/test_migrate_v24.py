"""Migration gate: a v23_s26-shaped schema-12 checkpoint migrated to 13
must (a) load cleanly (check_checkpoint-clean against the live layout) and
(b) produce action logits that are provably unaffected by this migration in
BOTH senses the plan's "bit-identical to the source model" bar requires:

* new-field inertness -- the migrated model, forward on a schema-13 obs,
  is invariant to whatever the new fields (event.options.*.ids ints,
  run.ascension float) contain, because the splice zero-columns them out;
* old-field preservation -- the migrated model, forward on the SOURCE
  checkpoint's own old-field values (carried into their new schema-13
  positions via ``migrate_runobs_v24.old_new_layouts``, new fields zeroed),
  produces logits matching the un-migrated SOURCE model forward on those
  same old-field values in their original schema-12 positions, to float32
  GEMM tolerance (not exact ``torch.equal`` -- see that test's own
  docstring for why cross-shape matmuls can't promise bit-identity even
  when correct) -- i.e. the block renumbering/splicing did not scramble
  anything.

Both checks run against the REAL seed checkpoint; both skip if it is
absent (CI-less repo, the .pt is gitignored)."""
import os
import subprocess
import sys

import numpy as np
import pytest
import torch

SRC = os.path.join("runs", "sts2_run_torch_v23_s26.pt")
pytestmark = pytest.mark.skipif(not os.path.exists(SRC),
                                 reason="seed checkpoint not present")


def _migrate(src, dst):
    r = subprocess.run(
        [sys.executable, os.path.join("tools", "migrate_runobs_v24.py"), src, dst],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_migrated_checkpoint_new_fields_are_inert(tmp_path):
    dst = str(tmp_path / "seed13.pt")
    _migrate(SRC, dst)

    from sts2_rl.checkpoints import load_agent
    from sts2_rl.run_env import N_ACTIONS, run_obs_layout
    from sts2_rl.tensor_obs import TensorObs

    ck = torch.load(dst, map_location="cpu", weights_only=False)
    assert ck["obs_schema"] == 13

    layout = run_obs_layout()
    obs_dim = (layout.f_dim, layout.i_dim)
    agent, _ckpt = load_agent(dst, env_kind="run", obs_dim=obs_dim, n_actions=N_ACTIONS)

    rng = np.random.default_rng(0)
    batch = 4
    f = rng.standard_normal((batch, layout.f_dim)).astype(np.float32)
    i = rng.integers(0, 5, (batch, layout.i_dim)).astype(np.int64)
    mask = torch.ones((batch, N_ACTIONS), dtype=torch.bool)

    tobs = TensorObs(f=torch.from_numpy(f), i=torch.from_numpy(i))

    ascension_sl = layout.f_slices["run.ascension"]
    option_names = [
        "event.options.cards.ids", "event.options.relics.ids",
        "event.options.relics_traded.ids", "event.options.potions.ids",
    ]
    option_slices = [layout.i_slices[n] for n in option_names]

    f2 = f.copy()
    i2 = i.copy()
    f2[:, ascension_sl] = 0.0
    for sl in option_slices:
        i2[:, sl] = 0

    tobs2 = TensorObs(f=torch.from_numpy(f2), i=torch.from_numpy(i2))

    with torch.no_grad():
        la = agent.action_logits(tobs, mask)
        lb = agent.action_logits(tobs2, mask)

    assert torch.equal(la, lb)


def test_migrated_checkpoint_matches_source_on_old_fields(tmp_path):
    """The plan's actual bar: identical to the SOURCE model, not just
    self-consistent post-migration. Builds a schema-12-shaped obs, forwards
    the un-migrated source checkpoint's own model on it, then forwards the
    migrated model on the same values relocated to their schema-13
    positions (new fields zeroed) and asserts the logits match to float32
    GEMM tolerance. A block-renumbering/scatter bug (this test's own first
    draft caught exactly one: the 4 fresh row blocks' zero columns landing
    scattered -- 160-192, 224-256, 288-320, 352-384 -- instead of one
    contiguous 160-288 span, corrupting real old-field columns in between)
    would pass the new-fields-inert test above but fail this one, with a
    large (~1.0) logit delta.

    Not ``torch.equal``: the source and migrated trunk Linears have
    DIFFERENT input widths (3253 vs 3382 columns for the real seed
    checkpoint), so even a mathematically-correct migration runs a
    differently-shaped GEMM, which IEEE-754 float32 accumulation is not
    required to reduce in the same order (verified against the real
    checkpoint after fixing the scatter bug above: max abs diff ~3e-5 at
    the first trunk layer, unlike the exact 0.0 you get comparing two
    passes through the SAME weight matrix, as
    ``test_migrated_checkpoint_new_fields_are_inert`` does above). The
    tolerance here is far tighter than the ~1.0 a real structural bug
    produces.
    """
    dst = str(tmp_path / "seed13.pt")
    _migrate(SRC, dst)

    from sts2_rl.checkpoints import (FRESH_TAIL_PREFIXES, ModelSpec, load_agent,
                                     load_model_state_lenient)
    from sts2_rl.models import EntitySetActorCritic, run_action_layout
    from sts2_rl.run_env import N_ACTIONS, run_obs_layout
    from sts2_rl.tensor_obs import TensorObs
    from tools.migrate_runobs_v24 import old_new_layouts

    src_ck = torch.load(SRC, map_location="cpu", weights_only=False)
    assert src_ck["obs_schema"] == 12

    spec = ModelSpec("run", arch="entset", hidden=tuple(src_ck["hidden"]),
                     shared_encoder=True)
    old_f_segs, old_i_segs, new_f_segs, new_i_segs = old_new_layouts(spec)

    src_model = EntitySetActorCritic(
        old_f_segs, old_i_segs, src_ck["n_actions"], run_action_layout(),
        hidden=tuple(src_ck["hidden"]), shared_encoder=True)
    # The frozen TAIL heads (aux_*/critic_q) grow generation over generation,
    # so a v23-era source checkpoint legitimately predates some of them and
    # they fresh-init on load. That is fine HERE: this test only compares
    # ``action_logits``, which no tail head feeds. What must NOT happen is an
    # OLD (pre-tail) parameter going missing -- that would mean the source
    # model is only partly loaded and the comparison below is vacuous. So
    # pin the leniency to the tail rather than to a count that ages out.
    missing = [k for k in src_model.state_dict() if k not in src_ck["model"]]
    assert all(k.startswith(FRESH_TAIL_PREFIXES) for k in missing), (
        f"source checkpoint is missing non-tail params: "
        f"{[k for k in missing if not k.startswith(FRESH_TAIL_PREFIXES)]}")
    n_fresh = load_model_state_lenient(src_model, src_ck["model"])
    assert n_fresh == len(missing)
    src_model.eval()

    layout = run_obs_layout()
    obs_dim = (layout.f_dim, layout.i_dim)
    migrated_agent, _ckpt = load_agent(
        dst, env_kind="run", obs_dim=obs_dim, n_actions=N_ACTIONS)

    # Shared random content, one array per OLD segment name -- placed into
    # the schema-12-shaped obs at its old position, and into the
    # schema-13-shaped obs at its new position. New-in-13 segments (4
    # event.options.*.ids blocks, run.ascension) get zeros in the new obs
    # and simply don't exist in the old one.
    rng = np.random.default_rng(0)
    batch = 4
    old_f_by_name = {n: rng.standard_normal((batch, w)).astype(np.float32)
                      for n, w in old_f_segs}
    old_i_by_name = {n: rng.integers(0, 5, (batch, w)).astype(np.int64)
                      for n, w in old_i_segs}

    old_f = np.concatenate([old_f_by_name[n] for n, _ in old_f_segs], axis=1)
    old_i = np.concatenate([old_i_by_name[n] for n, _ in old_i_segs], axis=1)

    new_f = np.concatenate(
        [old_f_by_name[n] if n in old_f_by_name else np.zeros((batch, w), dtype=np.float32)
         for n, w in new_f_segs], axis=1)
    new_i = np.concatenate(
        [old_i_by_name[n] if n in old_i_by_name else np.zeros((batch, w), dtype=np.int64)
         for n, w in new_i_segs], axis=1)

    assert old_f.shape[1] == sum(w for _, w in old_f_segs)
    assert new_f.shape[1] == layout.f_dim
    assert new_i.shape[1] == layout.i_dim

    src_obs = TensorObs(f=torch.from_numpy(old_f), i=torch.from_numpy(old_i))
    new_obs = TensorObs(f=torch.from_numpy(new_f), i=torch.from_numpy(new_i))
    mask = torch.ones((batch, N_ACTIONS), dtype=torch.bool)

    with torch.no_grad():
        src_logits = src_model.action_logits(src_obs, mask)
        migrated_logits = migrated_agent.action_logits(new_obs, mask)

    torch.testing.assert_close(src_logits, migrated_logits, atol=1e-3, rtol=1e-3)
