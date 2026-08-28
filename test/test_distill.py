"""test/test_distill.py — search-distillation tests (plan
2026-08-26-foresight-v25-v26).

Two independent sections live here:

  * **shard IO** (Task 10) — the on-disk contract between
    `tools/search_worker.py` (producer) and the trainer (consumer): dtypes,
    the −1 pad convention, and a bit-equal round trip. Pure numpy; needs
    neither a checkpoint nor a snapshot bank, so it runs in a fresh clone.
  * **distillation loss** (Task 11) — the trainer half: the preloading
    shard loader, the masked cross-entropy toward the search distribution,
    and the −1-pad agreement (a padded column must contribute EXACTLY zero
    gradient, which is the half of the producer/consumer contract Task 10
    could only assert on disk).

Anything that would need the local (gitignored) dev bank belongs behind the
`skipif` idiom of `test/test_forksim.py`, not here.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import search_worker


# ════════════════════════════════════════════════════════════════════════════
# Shard IO (Task 10)
# ════════════════════════════════════════════════════════════════════════════


def _synthetic(n=3, f_dim=11, i_dim=7, n_actions=5, k=4):
    """Three records with values chosen to be EXACTLY representable in the
    shard's dtypes (float16 has 11 bits of mantissa), so a round trip that
    loses nothing is bit-equal and a round trip that quietly re-casts is not.
    """
    rng = np.random.default_rng(0)
    f = (rng.integers(-64, 64, size=(n, f_dim)) / 8.0).astype(np.float16)
    i = rng.integers(0, 4096, size=(n, i_dim)).astype(np.int32)
    mask = rng.integers(0, 2, size=(n, n_actions)).astype(bool)
    tgt_idx = np.full((n, k), -1, dtype=np.int32)
    tgt_p = np.full((n, k), -1.0, dtype=np.float16)
    for r in range(n):
        kept = k - r                      # record r has a shorter candidate list
        tgt_idx[r, :kept] = np.arange(kept, dtype=np.int32)
        tgt_p[r, :kept] = np.float16(1.0 / kept)
    return f, i, mask, tgt_idx, tgt_p


def test_shard_round_trip_is_bit_equal(tmp_path):
    """Write a 3-record shard of known arrays, read it back through the
    loader, and assert every array is bit-identical and still in the shard's
    declared dtype."""
    f, i, mask, tgt_idx, tgt_p = _synthetic()
    path = tmp_path / "shard-00000.npz"
    search_worker.write_shard(path, f, i, mask, tgt_idx, tgt_p)

    shards = list(search_worker.iter_shards(tmp_path))
    assert len(shards) == 1
    got = shards[0]
    for name, want in (("f", f), ("i", i), ("mask", mask),
                       ("tgt_idx", tgt_idx), ("tgt_p", tgt_p)):
        assert got[name].dtype == want.dtype, name
        assert got[name].shape == want.shape, name
        # view as raw bytes: bit-equality, not float "closeness"
        assert got[name].tobytes() == want.tobytes(), name


def test_write_shard_casts_to_the_declared_dtypes(tmp_path):
    """The producer accumulates in whatever numpy hands it (obs `f` is
    float32, masks are bool arrays from the env); the SHARD's dtypes are
    fixed by the format, so the writer must cast rather than store float32."""
    f, i, mask, tgt_idx, tgt_p = _synthetic()
    path = tmp_path / "shard-00000.npz"
    search_worker.write_shard(path, f.astype(np.float32), i.astype(np.int64),
                              mask.astype(np.uint8), tgt_idx.astype(np.int64),
                              tgt_p.astype(np.float32))
    got = next(iter(search_worker.iter_shards(tmp_path)))
    assert (got["f"].dtype, got["i"].dtype, got["mask"].dtype,
            got["tgt_idx"].dtype, got["tgt_p"].dtype) == (
        np.dtype(np.float16), np.dtype(np.int32), np.dtype(bool),
        np.dtype(np.int32), np.dtype(np.float16))
    np.testing.assert_array_equal(got["mask"], mask)


def test_write_shard_rejects_ragged_records(tmp_path):
    f, i, mask, tgt_idx, tgt_p = _synthetic()
    with pytest.raises(ValueError):
        search_worker.write_shard(tmp_path / "s.npz", f[:2], i, mask,
                                  tgt_idx, tgt_p)


def test_iter_shards_reads_every_shard_in_filename_order(tmp_path):
    """A shard SET is the unit the trainer takes; the loader must return the
    shards in a stable order (records are ordered within a shard, so an
    unstable shard order would make a run's data order machine-dependent)."""
    f, i, mask, tgt_idx, tgt_p = _synthetic()
    for s in range(3):
        search_worker.write_shard(tmp_path / f"shard-{s:05d}.npz",
                                  f + np.float16(s), i, mask, tgt_idx, tgt_p)
    firsts = [float(sh["f"][0, 0]) for sh in search_worker.iter_shards(tmp_path)]
    assert firsts == [float(f[0, 0]) + s for s in range(3)]


def test_iter_shards_ignores_the_provenance_json(tmp_path):
    f, i, mask, tgt_idx, tgt_p = _synthetic()
    search_worker.write_shard(tmp_path / "shard-00000.npz", f, i, mask,
                              tgt_idx, tgt_p)
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")
    assert len(list(search_worker.iter_shards(tmp_path))) == 1


# ── targets: softmax over the searched candidates, −1 pad ───────────────────


def test_targets_are_a_temperature_1_softmax_renormalized_over_the_k():
    idx, p = search_worker.targets_from_scores((3, 1, 7), (1.0, 0.0, -1.0), k=5)
    assert idx.dtype == np.int32 and p.dtype == np.float16
    want = np.exp([1.0, 0.0, -1.0])
    want = want / want.sum()
    np.testing.assert_allclose(np.asarray(p[:3], dtype=np.float64), want,
                               rtol=1e-3, atol=1e-3)
    assert abs(float(np.asarray(p[:3], dtype=np.float64).sum()) - 1.0) < 1e-3


def test_targets_pad_with_minus_one_in_both_arrays():
    """Fewer candidates than k (a mass-capped or short-legal decision) pads
    BOTH arrays with −1: −1 is not a legal action id and not a probability,
    so the consumer's `tgt_idx >= 0` mask can never collide with real data."""
    idx, p = search_worker.targets_from_scores((2, 9), (0.5, 0.5), k=5)
    assert idx.tolist() == [2, 9, -1, -1, -1]
    assert [float(x) for x in p[2:]] == [-1.0, -1.0, -1.0]
    assert abs(float(p[0]) + float(p[1]) - 1.0) < 1e-3


def test_targets_are_shift_invariant_and_finite_on_large_scores():
    """Rollout scores are undiscounted-ish returns and can be large; the
    softmax must be the stable (max-subtracted) one or the targets become
    inf/nan."""
    idx, p = search_worker.targets_from_scores((0, 1), (900.0, 899.0), k=2)
    assert np.all(np.isfinite(np.asarray(p, dtype=np.float64)))
    assert idx.tolist() == [0, 1]
    base = search_worker.targets_from_scores((0, 1), (1.0, 0.0), k=2)[1]
    np.testing.assert_allclose(np.asarray(p, dtype=np.float64),
                               np.asarray(base, dtype=np.float64),
                               rtol=1e-2, atol=1e-3)


def test_targets_reject_more_candidates_than_k():
    with pytest.raises(ValueError):
        search_worker.targets_from_scores((0, 1, 2), (0.0, 0.0, 0.0), k=2)


# ── selection: elite/boss ∪ top-half entropy ────────────────────────────────


def test_masked_entropy_uses_legal_actions_only():
    probs = np.array([0.0, 0.5, 0.5, 0.0])
    mask = np.array([False, True, True, False])
    assert search_worker.masked_entropy(probs, mask) == pytest.approx(np.log(2))
    # a forced decision carries no entropy
    assert search_worker.masked_entropy(np.array([0.0, 1.0]),
                                        np.array([False, True])) == pytest.approx(0.0)


def test_selection_keeps_every_elite_and_boss_decision():
    rooms = ["ELITE", "MONSTER", "BOSS", "MONSTER"]
    ent = [0.0, 0.0, 0.0, 0.0]
    keep = search_worker.select_decisions(rooms, ent)
    assert keep[0] and keep[2]


def test_selection_adds_the_top_half_by_entropy():
    rooms = ["MONSTER"] * 4
    keep = search_worker.select_decisions(rooms, [0.1, 0.9, 0.2, 0.8])
    assert keep == [False, True, False, True]


def test_selection_rejects_a_rooms_entropies_length_mismatch():
    with pytest.raises(ValueError):
        search_worker.select_decisions(["MONSTER"], [0.1, 0.2])


# ── obs-contract plumbing: card_obs must reach every consumer ───────────────


def _args(**over):
    base = dict(ckpt="CKPT.pt", asc=10, card_obs="hybrid", device="cpu")
    base.update(over)
    return argparse.Namespace(**base)


def test_env_kwargs_carry_card_obs_to_every_env():
    """`--card-obs` must reach the drill env AND every `CombatFork` replay.
    Both build from this one dict, so testing it covers both."""
    for mode in ("hybrid", "features"):
        assert search_worker.env_kwargs_for(_args(card_obs=mode)) == {
            "ascension": 10, "card_obs": mode}


def test_the_env_actually_adopts_the_requested_card_obs():
    """The stamp-matches-actual-env invariant, end to end on the env side:
    the provenance `card_obs` is read off `env._card_obs`, so this asserts the
    kwargs really change the env's mode. This is NOT catchable by a dim check
    — both modes have identical f_dim/i_dim — which is exactly why a wrong
    stamp would go unnoticed."""
    from sts2_rl.run_env import STS2RunEnv, run_obs_layout

    for mode in ("hybrid", "features"):
        env = STS2RunEnv(**search_worker.env_kwargs_for(_args(card_obs=mode)))
        assert env._card_obs == mode
    # the invisibility this plumbing exists to compensate for
    assert ((run_obs_layout("hybrid").f_dim, run_obs_layout("hybrid").i_dim)
            == (run_obs_layout("features").f_dim, run_obs_layout("features").i_dim))


def test_policy_load_is_given_the_same_card_obs(monkeypatch):
    """`load_torch_policy` defaults to "hybrid"; omitting the flag there would
    decode the checkpoint against a different card encoding than the env
    produces, silently."""
    seen = {}

    def _fake(path, **kw):
        seen.update(kw, path=path)
        return object(), {}

    monkeypatch.setattr(search_worker, "load_torch_policy", _fake)
    env = object()
    search_worker.load_policy(_args(card_obs="features"), env)
    assert seen["card_obs"] == "features"
    assert seen["env"] is env and seen["env_kind"] == "run"
    assert seen["sample"] is True          # the reseed_policy trip hazard
    assert seen["path"] == "CKPT.pt"


def test_selection_median_split_is_over_the_whole_batch():
    """The threshold is the batch median including the elite/boss decisions —
    'top half of the batch' means the batch this invocation scored, not the
    non-elite remainder."""
    rooms = ["ELITE", "MONSTER", "MONSTER", "MONSTER"]
    keep = search_worker.select_decisions(rooms, [9.0, 0.1, 0.2, 0.3])
    # median of {9.0, 0.1, 0.2, 0.3} = 0.25 -> only 0.3 clears it
    assert keep == [True, False, False, True]


# ════════════════════════════════════════════════════════════════════════════
# Distillation loss (Task 11)
# ════════════════════════════════════════════════════════════════════════════
#
# The consumer half of the shard contract: `train_torch.load_distill_set`
# preloads a shard set onto the device once, and `train_torch.distill_loss`
# is the masked cross-entropy toward the search distribution that the PPO
# minibatch loop adds to the full loss.

import torch                                                    # noqa: E402

import train_torch                                              # noqa: E402
from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout  # noqa: E402
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS          # noqa: E402
from sts2_rl.tensor_obs import TensorObs                        # noqa: E402


def _tiny_entset():
    """A small run-kind entset agent + its obs dims — the same construction
    `test/test_aux_head.py::_build` uses (reuse, don't reinvent)."""
    spec = ModelSpec(env_kind="run", card_obs="hybrid", arch="entset",
                     hidden=(32,), shared_encoder=True)
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    return make_model(spec, obs_dim, RUN_N_ACTIONS), obs_dim, RUN_N_ACTIONS


def _rows(obs_dim, n_actions, targets, *, n_legal=8, k=2, seed=0):
    """`n = len(targets)` hand-built records: random obs, the first `n_legal`
    actions legal, and a ONE-HOT search target on `targets[r]`.

    `k` columns wide with only column 0 valid, so every record carries at
    least one −1 pad — the padding is not an edge case here, it is the
    default shape of the fixture.
    """
    rng = np.random.default_rng(seed)
    f_dim, i_dim = obs_dim
    n = len(targets)
    f = rng.standard_normal((n, f_dim)).astype(np.float16)
    i = np.zeros((n, i_dim), dtype=np.int32)
    mask = np.zeros((n, n_actions), dtype=bool)
    mask[:, :n_legal] = True
    tgt_idx = np.full((n, k), -1, dtype=np.int32)
    tgt_p = np.full((n, k), -1.0, dtype=np.float16)
    tgt_idx[:, 0] = np.asarray(targets, dtype=np.int32)
    tgt_p[:, 0] = np.float16(1.0)
    return f, i, mask, tgt_idx, tgt_p


def _set(obs_dim, n_actions, targets, **kw):
    arrays = _rows(obs_dim, n_actions, targets, **kw)
    return train_torch.DistillSet.from_arrays(*arrays, device="cpu")


# ── the loader: preload once, as device float32 ─────────────────────────────


def test_load_distill_set_preloads_every_shard_as_device_tensors(tmp_path):
    """The whole shard SET is materialized once at startup: float16 storage
    becomes float32, ids become int64 (embedding indices), and the records of
    every shard are concatenated in shard order."""
    f, i, mask, tgt_idx, tgt_p = _synthetic(n=3)
    for s in range(2):
        search_worker.write_shard(tmp_path / f"shard-{s:05d}.npz",
                                  f + np.float16(s), i, mask, tgt_idx, tgt_p)
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")

    ds = train_torch.load_distill_set(tmp_path, device="cpu")
    assert len(ds) == 6
    assert ds.f.dtype == torch.float32 and ds.i.dtype == torch.int64
    assert ds.mask.dtype == torch.bool
    assert ds.tgt_p.dtype == torch.float32
    assert ds.tgt_idx.dtype == torch.int64
    # shard order preserved: record 0 of shard 1 is shard 0's record 0 + 1
    assert float(ds.f[3, 0]) == pytest.approx(float(ds.f[0, 0]) + 1.0, abs=1e-2)


def test_load_distill_set_zeroes_the_pad_probabilities(tmp_path):
    """On disk a pad is −1 in BOTH arrays. In the loaded set the validity
    mask carries the padding and `tgt_p` is zeroed there, so no −1
    probability can ever reach the loss."""
    f, i, mask, tgt_idx, tgt_p = _synthetic(n=3)
    search_worker.write_shard(tmp_path / "shard-00000.npz", f, i, mask,
                              tgt_idx, tgt_p)
    ds = train_torch.load_distill_set(tmp_path, device="cpu")
    pad = ~ds.tgt_valid
    assert bool(pad.any())
    assert float(ds.tgt_p[pad].abs().max()) == 0.0
    assert torch.equal(ds.tgt_valid,
                       torch.as_tensor(tgt_idx, dtype=torch.int64) >= 0)
    # and every gather index is in range, padding included
    assert int(ds.tgt_idx.min()) >= 0


def test_load_distill_set_refuses_a_shard_set_of_the_wrong_shape(tmp_path):
    """A shard set is only meaningful against the obs schema it was written
    under; the dims are the one part of that the trainer can check cheaply."""
    f, i, mask, tgt_idx, tgt_p = _synthetic(n=2, f_dim=11, i_dim=7, n_actions=5)
    search_worker.write_shard(tmp_path / "shard-00000.npz", f, i, mask,
                              tgt_idx, tgt_p)
    with pytest.raises(SystemExit, match="distill"):
        train_torch.load_distill_set(tmp_path, device="cpu",
                                     obs_dim=(12, 7), n_actions=5)
    with pytest.raises(SystemExit, match="distill"):
        train_torch.load_distill_set(tmp_path, device="cpu",
                                     obs_dim=(11, 7), n_actions=6)
    # the matching contract loads fine
    assert len(train_torch.load_distill_set(
        tmp_path, device="cpu", obs_dim=(11, 7), n_actions=5)) == 2


def test_load_distill_set_refuses_an_empty_directory(tmp_path):
    with pytest.raises(SystemExit, match="distill"):
        train_torch.load_distill_set(tmp_path, device="cpu")


# ── the provenance check: the half the dims cannot carry ────────────────────


def _shards_with_provenance(tmp_path, prov, n=2):
    f, i, mask, tgt_idx, tgt_p = _synthetic(n=n, f_dim=11, i_dim=7, n_actions=5)
    search_worker.write_shard(tmp_path / "shard-00000.npz", f, i, mask,
                              tgt_idx, tgt_p)
    if prov is not None:
        (tmp_path / "provenance.json").write_text(json.dumps(prov),
                                                  encoding="utf-8")
    return dict(obs_dim=(11, 7), n_actions=5)


def test_load_distill_set_accepts_a_matching_provenance(tmp_path):
    dims = _shards_with_provenance(tmp_path, {"obs_schema": 13,
                                              "card_obs": "hybrid"})
    ds = train_torch.load_distill_set(tmp_path, device="cpu", obs_schema=13,
                                      card_obs="hybrid", **dims)
    assert len(ds) == 2


def test_load_distill_set_refuses_a_card_obs_mismatch(tmp_path):
    """The failure this check exists for: `hybrid` and `features` have
    IDENTICAL f/i dims at schema 13, so the dim check cannot separate them
    and a mis-encoded shard set would train to a plausible loss curve."""
    dims = _shards_with_provenance(tmp_path, {"obs_schema": 13,
                                              "card_obs": "features"})
    with pytest.raises(SystemExit, match="card_obs"):
        train_torch.load_distill_set(tmp_path, device="cpu", obs_schema=13,
                                     card_obs="hybrid", **dims)


def test_load_distill_set_refuses_an_obs_schema_mismatch(tmp_path):
    dims = _shards_with_provenance(tmp_path, {"obs_schema": 12,
                                              "card_obs": "hybrid"})
    with pytest.raises(SystemExit, match="obs_schema"):
        train_torch.load_distill_set(tmp_path, device="cpu", obs_schema=13,
                                     card_obs="hybrid", **dims)


def test_load_distill_set_refuses_a_missing_provenance(tmp_path):
    """`tools/search_worker.py` ALWAYS writes one, so its absence means the
    directory is not a shard set the trainer can vouch for. Refuse — the
    safe default for an unverifiable set."""
    dims = _shards_with_provenance(tmp_path, None)
    with pytest.raises(SystemExit, match="provenance.json"):
        train_torch.load_distill_set(tmp_path, device="cpu", obs_schema=13,
                                     card_obs="hybrid", **dims)


def test_load_distill_set_refuses_an_unstamped_provenance(tmp_path):
    """A stamp that isn't there cannot be compared, so a provenance file
    missing the keys is refused exactly like a missing file."""
    dims = _shards_with_provenance(tmp_path, {"k": 5})
    with pytest.raises(SystemExit, match="obs_schema"):
        train_torch.load_distill_set(tmp_path, device="cpu", obs_schema=13,
                                     card_obs="hybrid", **dims)


def test_the_provenance_check_is_off_only_when_no_contract_is_declared(tmp_path):
    """A hand-built shard set (no provenance) still loads when the caller
    declares no schema/card-obs — there is nothing for it to disagree with.
    The trainer always declares both, so this leniency never reaches a run."""
    dims = _shards_with_provenance(tmp_path, None)
    assert len(train_torch.load_distill_set(tmp_path, device="cpu", **dims)) == 2


# ── the loss ────────────────────────────────────────────────────────────────


def test_distill_loss_falls_after_50_adam_steps():
    """The brief's gate: 4 hand-built rows with a one-hot search target on a
    legal action, 50 Adam steps on a tiny entset model, loss must fall."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    ds = _set(obs_dim, n_actions, [0, 1, 2, 3])
    rows = torch.arange(len(ds))

    opt = torch.optim.Adam(agent.parameters(), lr=3e-3)
    first = float(train_torch.distill_loss(agent, ds, rows).item())
    for _ in range(50):
        loss = train_torch.distill_loss(agent, ds, rows)
        opt.zero_grad()
        loss.backward()
        opt.step()
    last = float(train_torch.distill_loss(agent, ds, rows).item())
    assert last < first, f"distill loss did not fall: {first} -> {last}"
    # and it has actually moved the policy toward the searched actions
    with torch.no_grad():
        logits = agent.action_logits(TensorObs(ds.f, ds.i), ds.mask)
    assert logits.argmax(-1).tolist() == [0, 1, 2, 3]


def test_a_minus_one_padded_column_contributes_exactly_zero_gradient():
    """The producer/consumer −1-pad agreement, closed on the consumer side:
    padding a record out to a wider `k` must change NEITHER the loss NOR any
    parameter gradient, bit for bit."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    narrow = _set(obs_dim, n_actions, [0, 1, 2, 3], k=1)
    wide = _set(obs_dim, n_actions, [0, 1, 2, 3], k=5)
    assert bool(wide.tgt_valid[:, 1:].any()) is False
    rows = torch.arange(4)

    def grads(ds):
        agent.zero_grad(set_to_none=True)
        loss = train_torch.distill_loss(agent, ds, rows)
        loss.backward()
        return float(loss.item()), {n: p.grad.detach().clone()
                                    for n, p in agent.named_parameters()
                                    if p.grad is not None}

    l_narrow, g_narrow = grads(narrow)
    l_wide, g_wide = grads(wide)
    assert l_wide == l_narrow
    assert set(g_wide) == set(g_narrow)
    for name in g_narrow:
        assert torch.equal(g_wide[name], g_narrow[name]), name


def test_a_pad_never_reads_the_action_it_clamps_to():
    """A −1 index cannot be handed to `gather`, so the consumer clamps it —
    which means the pad column mechanically LANDS on some real action's
    log-prob. Make that action ILLEGAL in the shard's own mask (its masked
    log-prob is hugely negative): the loss must stay finite and unchanged."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    f, i, mask, tgt_idx, tgt_p = _rows(obs_dim, n_actions, [3, 4, 5, 6], k=4)
    mask[:, 0] = False                      # action 0 = where a pad clamps to
    ds = train_torch.DistillSet.from_arrays(f, i, mask, tgt_idx, tgt_p,
                                            device="cpu")
    rows = torch.arange(4)
    loss = train_torch.distill_loss(agent, ds, rows)
    loss.backward()
    assert torch.isfinite(loss)
    assert all(torch.isfinite(p.grad).all()
               for p in agent.parameters() if p.grad is not None)
    # identical to the same records with no pad columns at all
    ds1 = train_torch.DistillSet.from_arrays(f, i, mask, tgt_idx[:, :1],
                                             tgt_p[:, :1], device="cpu")
    assert float(train_torch.distill_loss(agent, ds1, rows).item()) \
        == float(loss.item())


def test_distill_loss_is_the_masked_cross_entropy_the_brief_specifies():
    """Value check against the formula written out by hand:
    `-(tgt_p * log_softmax(action_logits(obs, mask)))[tgt_idx].sum(-1).mean()`,
    with log_softmax taken over the SHARD's own mask."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    ds = _set(obs_dim, n_actions, [0, 1, 2, 3], k=3)
    rows = torch.arange(4)
    got = float(train_torch.distill_loss(agent, ds, rows).item())
    with torch.no_grad():
        logp = torch.log_softmax(
            agent.action_logits(TensorObs(ds.f, ds.i), ds.mask), dim=-1)
    want = -float(sum(logp[r, t] for r, t in enumerate([0, 1, 2, 3])) / 4.0)
    assert got == pytest.approx(want, abs=1e-5)


def test_distill_loss_respects_the_shards_own_mask():
    """The log-softmax normalizes over the legality vector STORED WITH THE
    RECORD, not over the full action vector: widening the shard's mask must
    change the loss."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    narrow = _set(obs_dim, n_actions, [0, 1, 2, 3], n_legal=8)
    wide = _set(obs_dim, n_actions, [0, 1, 2, 3], n_legal=64)
    rows = torch.arange(4)
    a = float(train_torch.distill_loss(agent, narrow, rows).item())
    b = float(train_torch.distill_loss(agent, wide, rows).item())
    assert a != b and b > a          # more legal mass to spread over


def test_distill_gradients_reach_the_actor_and_not_the_critic():
    """The point of the term is that it trains the SAME actor PPO trains —
    the shared encoder and the action heads — and nothing else. The critic
    heads are not in this graph at all, so their grads stay None."""
    torch.manual_seed(0)
    agent, obs_dim, n_actions = _tiny_entset()
    ds = _set(obs_dim, n_actions, [0, 1, 2, 3])
    train_torch.distill_loss(agent, ds, torch.arange(4)).backward()
    touched = {n for n, p in agent.named_parameters() if p.grad is not None}
    assert any(n.startswith("actor_encoder.") for n in touched)
    assert any(n.startswith("actor.") for n in touched)
    assert any("head" in n for n in touched)
    assert not any(n.startswith("critic") for n in touched)
    assert not any(n.startswith("aux_") for n in touched)


def test_sampled_rows_are_uniform_with_replacement_and_capped():
    """Per PPO minibatch the term costs `min(mb_size, 4096)` rows drawn
    uniformly WITH replacement from the whole set — not an epoch over the
    shards, so the cost per update is bounded no matter how big the set is."""
    g = torch.Generator().manual_seed(0)
    rows = train_torch.sample_distill_rows(100, 8192, device="cpu", generator=g)
    assert rows.shape == (4096,)
    assert int(rows.min()) >= 0 and int(rows.max()) < 100
    assert len(set(rows.tolist())) <= 100          # with replacement
    small = train_torch.sample_distill_rows(1000, 64, device="cpu", generator=g)
    assert small.shape == (64,)


# ── flags, guards, CSV ──────────────────────────────────────────────────────


def test_distill_flags_default_off(monkeypatch):
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--arch", "entset"])
    args = train_torch.parse_args()
    assert args.distill is None
    assert args.distill_coef == 0.0


def test_distill_needs_the_run_env_and_entset(monkeypatch):
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--arch", "entset",
                                     "--distill", "runs/distill/x",
                                     "--distill-coef", "1.0"])
    with pytest.raises(SystemExit, match="distill"):
        train_torch.parse_args()
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--arch", "mlp",
                                     "--distill", "runs/distill/x",
                                     "--distill-coef", "1.0"])
    with pytest.raises(SystemExit, match="distill"):
        train_torch.parse_args()


def test_distill_coef_without_a_directory_is_refused(monkeypatch):
    """A coef with no shards is a silently-inert run — the exact failure the
    guard style in this file exists to prevent."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--arch", "entset",
                                     "--distill-coef", "1.0"])
    with pytest.raises(SystemExit, match="distill"):
        train_torch.parse_args()


def test_distill_has_a_csv_column():
    """NaN-when-off, same convention as `aux_win`/`aux_turn`."""
    assert "distill" in train_torch.CSV_FIELDS
