"""Tests for the three PPO architectures (sts2_rl/models.py) and the
train_torch checkpoint arch stamping.

There are three ``--arch`` choices now (T6 of prompts/entity-obs-schema.md):

* ``mlp`` / ``entity`` -- the frozen v3-era designs. Both still WORK against
  the v4 ``{"f", "i"}`` envs (models.py's own module docstring: "a deliberate
  degeneration, not a bug") by flattening a :class:`~sts2_rl.tensor_obs.TensorObs`
  to ``concat(f, i.float())`` and treating every id as a plain number --
  ``entity``'s embedding-table machinery matches segments by v3-era
  name-suffix/width conventions the v4 layout no longer has, so on the real
  envs it builds ZERO tables and degenerates to exactly ``mlp``. This file
  keeps the generic forward/mask/determinism coverage those two archs still
  deserve as thin wrappers over the same masked-categorical contract, but
  drops the assertions that depended on ``entity`` actually building
  embedding tables against the current layout -- see
  ``test_entset_*`` below for where that property now lives, and the
  docstring on the test it replaced for why.
* ``entset`` -- the v4 replacement (OBS_SCHEMA.md Sec.2.2): consumes the
  ``{"f", "i"}`` pair directly via one ``nn.Embedding(capacity + 1, dim,
  padding_idx=0)`` table per vocabulary kind and a masked sum-pool per row
  block. This is the arch actually exercised against the real env layouts.
"""
from __future__ import annotations

import random
from argparse import Namespace

import numpy as np
import pytest
import torch

import train_torch
from sts2_rl import checkpoints, models
from sts2_rl.checkpoints import ModelSpec, model_obs_layout, model_obs_segments
from sts2_rl.full_env import MAX_POTIONS, STS2FullCombatEnv, combat_obs_layout
from sts2_rl.models import (
    EntityActorCritic,
    EntitySetActorCritic,
    MaskedActorCritic,
    combat_action_layout,
    run_action_layout,
)
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.tensor_obs import TensorObs
from sts2_rl.vocab import CAPACITIES

COMBAT_N_ACTIONS = 79
COMBAT_LAYOUT = combat_action_layout(MAX_POTIONS)
RUN_LAYOUT = run_action_layout()


def combat_segments() -> list[tuple[str, int]]:
    """``entity``'s frozen v3-era flat-obs segment list against the REAL
    combat layout -- ``checkpoints.model_obs_segments`` is the same helper
    ``make_model``/``train_torch.env_obs_segments`` build from in
    production, so this can't drift from what a real ``--arch entity`` run
    actually sees."""
    return model_obs_segments(ModelSpec("combat", arch="entity"))


def run_segments() -> list[tuple[str, int]]:
    """Ditto for the run-scale layout. ``run_obs_layout`` already folds the
    combat block in under a ``"combat."`` prefix (OBS_SCHEMA.md Sec.5A), so
    -- unlike the old flat-obs world -- no manual composition of "run
    segments plus combat segments" is needed here any more."""
    return model_obs_segments(ModelSpec("run", arch="entity"))


def make_entity(segments=None, n_actions=COMBAT_N_ACTIONS, hidden=(32,)):
    segs = combat_segments() if segments is None else segments
    return EntityActorCritic(segs, n_actions, hidden=hidden)


def rand_obs_mask(model, batch=4, seed=0):
    g = torch.Generator().manual_seed(seed)
    obs = torch.rand((batch, model.obs_dim), generator=g)
    mask = torch.zeros((batch, model.n_actions), dtype=torch.bool)
    rng = random.Random(seed)
    for b in range(batch):
        mask[b, rng.sample(range(model.n_actions), 5)] = True
    return obs, mask


# ── mlp / entity: generic forward/mask/determinism contract ─────────────────
#
# None of these five care about WHAT the observation means -- they exercise
# the masked-categorical API (`get_action_and_value`/`get_value`) any arch
# must satisfy, feeding it a plain flat tensor exactly as `models._as_flat`
# passes a bare `torch.Tensor` through unchanged. That property survived the
# v4 migration untouched, so these needed no rewrite beyond `combat_segments`
# now sourcing the real layout instead of the retired `full_env.obs_segments`.


def test_obs_dim_matches_segment_sum():
    model = make_entity()
    assert model.obs_dim == sum(w for _, w in combat_segments())
    assert model.n_actions == COMBAT_N_ACTIONS


def test_forward_shapes():
    model = make_entity()
    obs, mask = rand_obs_mask(model, batch=5)
    action, logp, entropy, value = model.get_action_and_value(obs, mask)
    assert action.shape == (5,)
    assert logp.shape == (5,)
    assert entropy.shape == (5,)
    assert value.shape == (5,)
    assert model.get_value(obs).shape == (5,)


def test_sampled_actions_respect_mask():
    model = make_entity()
    obs, mask = rand_obs_mask(model, batch=64, seed=1)
    torch.manual_seed(0)
    action, _, _, _ = model.get_action_and_value(obs, mask)
    assert mask[torch.arange(64), action].all()


def test_illegal_action_gets_near_zero_probability():
    model = make_entity()
    obs, mask = rand_obs_mask(model, batch=4, seed=2)
    illegal = (~mask[0]).nonzero()[0].item()
    forced = torch.full((4,), illegal, dtype=torch.long)
    _, logp, _, _ = model.get_action_and_value(obs, mask, forced)
    assert (logp < -20.0).all()


def test_determinism_under_seed():
    torch.manual_seed(7)
    m1 = make_entity()
    torch.manual_seed(7)
    m2 = make_entity()
    obs, mask = rand_obs_mask(m1, batch=4, seed=4)
    assert torch.equal(m1.get_value(obs), m2.get_value(obs))
    torch.manual_seed(11)
    a1, lp1, _, _ = m1.get_action_and_value(obs, mask)
    torch.manual_seed(11)
    a2, lp2, _, _ = m2.get_action_and_value(obs, mask)
    assert torch.equal(a1, a2)
    assert torch.equal(lp1, lp2)


def test_run_layout_builds_and_runs():
    segs = run_segments()
    model = make_entity(segs, n_actions=RUN_N_ACTIONS)
    assert model.obs_dim == sum(w for _, w in segs)
    obs, mask = rand_obs_mask(model, batch=3, seed=3)
    action, logp, entropy, value = model.get_action_and_value(obs, mask)
    assert action.shape == (3,)
    assert value.shape == (3,)


def test_entity_degenerates_to_zero_tables_against_the_v4_layout():
    """Pins the documented (models.py module docstring) degeneration itself,
    rather than just relying on prose: against the real v4 layout, `entity`'s
    `_SegmentEncoder` builds NO embedding tables at all (every segment name
    the v3-era `_segment_plan` recognises -- `.onehot`, a bare `.powers` of
    width `3 * N_POWERS`, `.identity`, ... -- was split into separate
    `.ids`/`.f` blocks by the v4 rewrite, so nothing matches any more) and
    the encoder's input/output width are identical, i.e. pure pass-through.
    This is what makes `entity` parameter-IDENTICAL to `mlp` now (see the
    docstring on `test_entset_strictly_smaller_than_mlp_on_the_real_layout`,
    which is where the old `test_entity_strictly_smaller_than_mlp`'s property
    moved) -- a fact worth pinning directly, since a future segment-plan fix
    that silently stopped degenerating would be a real behavior change this
    file should catch."""
    model = make_entity()
    encoder = model.actor_encoder
    assert dict(encoder.tables) == {}
    assert encoder.out_dim == encoder.in_dim == model.obs_dim


# ── train_torch / checkpoints: the three-arch factory ────────────────────────


def _combat_args(tmp_path, arch: str) -> Namespace:
    return Namespace(
        env="combat", arch=arch, card_obs="hybrid",
        hidden=[32], save=str(tmp_path / "ckpt.pt"),
        n_envs=train_torch.DEFAULT_N_ENVS, n_steps=train_torch.DEFAULT_N_STEPS,
    )


def _combat_obs_dim() -> tuple[int, int]:
    """The real combat env's ``(f_dim, i_dim)`` pair -- what every
    ``checkpoints.make_model`` call site is keyed on now that
    ``observation_space`` is a ``spaces.Dict`` (OBS_SCHEMA.md Sec.2), not a
    single flat int."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat"))
    return sum(w for _, w in f_segments), sum(w for _, w in i_segments)


def test_make_model_factory(tmp_path):
    """``mlp``/``entity`` are refused against the real (v4-schema) combat
    env -- final fix-pass review item 2: `models._as_flat`'s unnormalized
    `concat(f, i)` lets ids up to 640 swamp the ~1400 genuinely numeric
    floats, and this project keeps no old-vs-new comparison baseline that
    would justify still building them. ``entset`` is the only arch this
    factory still builds against a real env layout; the frozen classes
    themselves stay directly testable (`make_entity`, `MaskedActorCritic`
    unit tests elsewhere in this file) -- this test used to pin the
    opposite (both still buildable, `entity` degenerating to `mlp`), which
    is exactly the behavior review item 2 settled as wrong."""
    obs_dim = _combat_obs_dim()
    with pytest.raises(SystemExit, match="entset"):
        train_torch.make_model(_combat_args(tmp_path, "mlp"), obs_dim, COMBAT_N_ACTIONS)
    with pytest.raises(SystemExit, match="entset"):
        train_torch.make_model(_combat_args(tmp_path, "entity"), obs_dim, COMBAT_N_ACTIONS)
    entset = train_torch.make_model(
        _combat_args(tmp_path, "entset"), obs_dim, COMBAT_N_ACTIONS)
    assert isinstance(entset, EntitySetActorCritic)
    assert entset.obs_dim == obs_dim


def test_make_model_refuses_future_v4_generation_schema(tmp_path, monkeypatch):
    """Pins the property that made this refusal break once already: the
    combat obs schema bumped 4 -> 5 (a new intent-card-count float) and the
    ``mlp``/``entity`` refusal above silently stopped firing, because it used
    to be ``obs_schema_version(spec) in frozenset({4, 7})`` -- an enumeration
    of "known" versions that a new, unlisted version falls outside of.
    ``checkpoints._is_v4_generation`` replaced that with a ``>=`` threshold
    per env_kind, which by construction can never exclude a later version.
    Proven here by monkeypatching ``obs_schema_version`` to a schema far
    beyond anything this repo has shipped (simulating many future bumps, not
    just the next one) and confirming the refusal still fires -- if a future
    change reverts to an enumerated set, this goes green-to-red immediately
    without anyone needing to remember to update a literal."""
    import sts2_rl.checkpoints as checkpoints_mod

    monkeypatch.setattr(checkpoints_mod, "obs_schema_version", lambda spec: 999)
    obs_dim = _combat_obs_dim()
    with pytest.raises(SystemExit, match="entset"):
        train_torch.make_model(_combat_args(tmp_path, "mlp"), obs_dim, COMBAT_N_ACTIONS)
    with pytest.raises(SystemExit, match="entset"):
        train_torch.make_model(_combat_args(tmp_path, "entity"), obs_dim, COMBAT_N_ACTIONS)
    # entset is never subject to the refusal, at any schema number.
    entset = train_torch.make_model(
        _combat_args(tmp_path, "entset"), obs_dim, COMBAT_N_ACTIONS)
    assert isinstance(entset, EntitySetActorCritic)


def test_checkpoint_roundtrip_and_arch_refusal(tmp_path):
    args = _combat_args(tmp_path, "entity")
    obs_dim = sum(w for _, w in combat_segments())
    model = make_entity(hidden=(32,))
    optimizer = torch.optim.Adam(model.parameters())
    train_torch.save(model, optimizer, 3, args)

    ckpt = torch.load(args.save, map_location="cpu", weights_only=False)
    assert ckpt["arch"] == "entity"
    assert ckpt["iteration"] == 3

    # Matching arch: accepted, and weights round-trip exactly.
    train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)
    reloaded = make_entity(hidden=(32,))
    reloaded.load_state_dict(ckpt["model"])
    obs, _ = rand_obs_mask(model, batch=2, seed=5)
    assert torch.equal(model.get_value(obs), reloaded.get_value(obs))

    # Arch mismatch: refused with a clear message.
    with pytest.raises(SystemExit, match="arch"):
        train_torch.check_checkpoint(
            ckpt, _combat_args(tmp_path, "mlp"), obs_dim, COMBAT_N_ACTIONS)

    # Old MLP checkpoints carry no arch key: treated as "mlp", so an entity
    # run refuses them.
    legacy = dict(ckpt)
    del legacy["arch"]
    with pytest.raises(SystemExit, match="arch"):
        train_torch.check_checkpoint(legacy, args, obs_dim, COMBAT_N_ACTIONS)


# ── entset: the v4 architecture, exercised against the REAL env layouts ─────


def _batch(obs: dict, mask) -> tuple[TensorObs, torch.Tensor]:
    tobs = TensorObs.from_dict(obs, device="cpu")[None]
    maskt = torch.as_tensor(mask, dtype=torch.bool).unsqueeze(0)
    return tobs, maskt


def test_entset_builds_and_forwards_on_the_real_combat_layout():
    """`entset` consumes a REAL `STS2FullCombatEnv` observation end to end --
    not a synthetic random tensor like the mlp/entity tests above, since the
    whole point of the row/embedding encoder is that it depends on the
    layout's actual segment names and widths agreeing with the ids the env
    really emits (`entset_segment_plan`'s own completeness check)."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    model = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))

    env = STS2FullCombatEnv()
    obs, _info = env.reset(seed=0)
    mask = env.action_masks()
    tobs, maskt = _batch(obs, mask)

    action, logp, entropy, value = model.get_action_and_value(tobs, maskt)
    assert action.shape == (1,)
    assert logp.shape == entropy.shape == value.shape == (1,)
    assert model.get_value(tobs).shape == (1,)
    assert mask[int(action.item())], "a legal action must remain legal after masking"

    # Exercise step() too, not just reset() -- a fresh combat state and a
    # mid-combat one must both flow through the encoder without shape errors.
    obs2, *_ = env.step(int(np.flatnonzero(mask)[0]))
    mask2 = env.action_masks()
    tobs2, maskt2 = _batch(obs2, mask2)
    model.get_action_and_value(tobs2, maskt2)


def test_entset_builds_and_forwards_on_the_real_run_layout():
    """Ditto for the run-scale layout (`run_obs_layout`'s combat block
    folded in under `"combat."`, OBS_SCHEMA.md Sec.5A) -- a real
    `STS2RunEnv` episode start, not a hand-built `RunState`/`DecisionRequest`
    surgery fixture, so this exercises the SAME obs the trainer's own
    `envs.reset()` produces."""
    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    model = EntitySetActorCritic(f_segments, i_segments, RUN_N_ACTIONS, RUN_LAYOUT, hidden=(32,))

    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    mask = env.action_masks()
    tobs, maskt = _batch(obs, mask)

    action, logp, entropy, value = model.get_action_and_value(tobs, maskt)
    assert action.shape == (1,)
    assert logp.shape == entropy.shape == value.shape == (1,)
    assert mask[int(action.item())]


def test_entset_batches_multiple_observations_independently():
    """A batch of >1 real observations must forward without any cross-talk
    between rows -- each row's masked sum-pool only ever reads that row's own
    slice, so stacking two DIFFERENT combats must not just run but produce
    per-row outputs that respond to per-row differences (a batch dim that
    silently broadcast/aliased one env's obs onto another's mask would still
    produce the right SHAPES, so shape-only assertions can't catch this)."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    model = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))

    env_a, env_b = STS2FullCombatEnv(), STS2FullCombatEnv()
    obs_a, _ = env_a.reset(seed=0)
    obs_b, _ = env_b.reset(seed=1)
    mask_a, mask_b = env_a.action_masks(), env_b.action_masks()
    assert not (mask_a == mask_b).all(), "fixture sanity: the two seeds must actually differ"

    f = torch.as_tensor(np.stack([obs_a["f"], obs_b["f"]]), dtype=torch.float32)
    i = torch.as_tensor(np.stack([obs_a["i"], obs_b["i"]]), dtype=torch.int64)
    mask = torch.as_tensor(np.stack([mask_a, mask_b]), dtype=torch.bool)
    batched = TensorObs(f, i)

    values = model.get_value(batched)
    assert values.shape == (2,)

    single_a = model.get_value(TensorObs(f[:1], i[:1]))
    single_b = model.get_value(TensorObs(f[1:], i[1:]))
    torch.testing.assert_close(values, torch.cat([single_a, single_b]))


def test_entset_embedding_tables_sized_to_capacities():
    """The porting-safe property `test_embedding_tables_sized_to_capacities`
    used to pin against `entity`'s v3-era design now belongs to `entset`
    (see `test_entity_degenerates_to_zero_tables_against_the_v4_layout`
    above for why `entity` no longer builds tables at all): one row per
    frozen vocab id PLUS a padding row (`capacity + 1`, OBS_SCHEMA.md
    Sec.2.1 -- id 0 reserved for PAD, `padding_idx=0`), sized to the
    reserved CAPACITY rather than the live count, so porting content only
    ever appends rows and never reshapes weights. The run layout touches
    every vocabulary kind, including the two v4 added (afflictions/
    enchantments) that `entity`'s frozen `EMBED_DIMS` never had."""
    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    model = EntitySetActorCritic(f_segments, i_segments, RUN_N_ACTIONS, RUN_LAYOUT, hidden=(32,))
    for enc in (model.actor_encoder, model.critic_encoder):
        for kind, cap in CAPACITIES.items():
            table = enc.tables[kind]
            assert table.num_embeddings == cap + 1, kind
            assert table.padding_idx == 0
            assert torch.all(table.weight[0] == 0.0), (
                f"{kind}: the padding row must stay the zero vector")


def test_entset_strictly_smaller_than_mlp_on_the_real_layout():
    """The parameter-savings property the old, now-deleted
    `test_entity_strictly_smaller_than_mlp` pinned: an embedding
    architecture needs far fewer parameters than a raw MLP swallowing the
    full observation width one column per scalar. That property genuinely
    stopped holding for `--arch entity` against the v4 layout -- confirmed
    directly, `entity` and `mlp` both come out to exactly 131152 parameters
    for `hidden=(32,)` on the real combat layout, because `entity` now
    builds zero embedding tables (see the degeneration test above) and is
    therefore not "smaller", just IDENTICAL. `entset` is the v4 arch that
    actually owns the embedding-compression property now, so this is where
    the test moved rather than a value quietly dropped.

    T7 brief (tied action head): the tied heads (two `PairPointerHead`
    instances, each with their own fixed-size MLP) add a roughly
    trunk-size-INDEPENDENT parameter cost on top of the encoder -- at the
    tiny `hidden=(32,)` every other test in this file uses for speed, that
    fixed cost actually pushes `entset` (153444 params) ABOVE `mlp`
    (148816): measured directly, not assumed. The compression property is
    real at the trunk width this project actually trains with
    (`hidden=(256,256)`: entset 634916 < mlp 1321552, measured), so this
    test moved to that width -- it was never about `hidden=(32,)` specifically,
    that was just every other test's speed shortcut. Construction-only (no
    forward), so the wider trunk costs nothing in test runtime."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    flat_dim = sum(w for _, w in f_segments) + sum(w for _, w in i_segments)
    hidden = (256, 256)
    mlp = MaskedActorCritic(flat_dim, COMBAT_N_ACTIONS, hidden=hidden)
    entset = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=hidden)
    n_mlp = sum(p.numel() for p in mlp.parameters())
    n_entset = sum(p.numel() for p in entset.parameters())
    assert n_entset < n_mlp


def test_entset_determinism_under_seed():
    """Same seed -> same weights -> same greedy choices, mirroring
    `test_determinism_under_seed` above for the row/embedding arch (its
    embedding tables are the one piece of state that test never touched)."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))

    torch.manual_seed(7)
    m1 = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))
    torch.manual_seed(7)
    m2 = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))

    env = STS2FullCombatEnv()
    obs, _ = env.reset(seed=0)
    mask = env.action_masks()
    tobs, maskt = _batch(obs, mask)

    assert torch.equal(m1.get_value(tobs), m2.get_value(tobs))
    torch.manual_seed(11)
    a1, lp1, _, _ = m1.get_action_and_value(tobs, maskt)
    torch.manual_seed(11)
    a2, lp2, _, _ = m2.get_action_and_value(tobs, maskt)
    assert torch.equal(a1, a2)
    assert torch.equal(lp1, lp2)


# ── entset: the presence mask must implement OBS_SCHEMA.md Sec.2.1's actual
#    definition, not half of it ───────────────────────────────────────────
#
# Sec.2.1 rule 2: "a padded row is id == 0 AND all-zero floats" -- present is
# the negation of THAT conjunction, i.e. `id != 0 OR any float nonzero`. The
# encoder's mask used to test only the id column (`_EntsetEncoder.forward`'s
# `mask = (ids[..., meta["primary"]] != 0)`), which silently drops any row
# that has a PAD id but live floats. Two real blocks are exactly that shape
# -- each side of the seam (env vs. encoder) was individually correct, which
# is why this survived four separate per-lane reviews; only a whole-branch
# pass could see the join.


def test_hand_block_is_visible_under_card_obs_features():
    """`--card-obs features` (`full_env.py`'s `_hand_rows`) writes
    `card_id = PAD` for every REAL card in hand, by design -- the card's
    identity is meant to reach the model only through its 29-float feature
    row, not a `cards` embedding. An id-only presence mask can't tell that
    row apart from a genuinely empty hand slot (also PAD id, but all-zero
    floats) and drops both, so the whole `hand` block pools to the zero
    vector -- the policy cannot see its own hand. Measured on a real env:
    the hand block's pooled contribution is 0.0 in `features` mode vs 29.13
    in `hybrid`."""
    f_segments, i_segments = model_obs_layout(
        ModelSpec("combat", arch="entset", card_obs="features"))
    model = EntitySetActorCritic(f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))

    env = STS2FullCombatEnv(card_obs="features")
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]

    pooled = model.actor_encoder(tobs)
    start, stop = model.actor_encoder.out_spans["hand"]
    hand_contribution = pooled[..., start:stop]
    assert hand_contribution.abs().sum().item() > 0, (
        "hand's pooled contribution is exactly zero under --card-obs "
        "features -- every hand row is being masked away because the mask "
        "only checks the (PAD, by design in this mode) card_id column and "
        "ignores the row's 29 live floats")


def test_run_potions_empty_slot_is_visible():
    """`run.potions` rows are `(present, slot_exists)` (OBS_SCHEMA.md
    Sec.5A). An empty-but-existing belt slot writes `id=PAD, floats=[0.0,
    1.0]` -- `slot_exists` is the only reason that second float exists at
    all. An id-only presence mask discards it for every empty slot (measured
    by the reviewer: 833 such rows across 5 real run episodes). A fresh run
    starts with an empty belt, so every one of its base slots is exactly
    this shape -- not a synthetic corner case."""
    f_segments, i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    model = EntitySetActorCritic(f_segments, i_segments, RUN_N_ACTIONS, RUN_LAYOUT, hidden=(32,))

    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]

    pooled = model.actor_encoder(tobs)
    start, stop = model.actor_encoder.out_spans["run.potions"]
    potions_contribution = pooled[..., start:stop]
    assert potions_contribution.abs().sum().item() > 0, (
        "run.potions's pooled contribution is exactly zero on a fresh run "
        "-- every empty belt slot's slot_exists float is being masked away "
        "because the mask only checks the (PAD, by design) potion id "
        "column")


# ── head_version: honest checkpoint refusal for the tied action head ─────
#
# T7 rebuilt the entset action head IN PLACE -- same "entset" arch string,
# same (obs_dim, n_actions, hidden) triple -- from a positional
# `Linear(hidden, n_actions)` to the tied `ActionLayout` / `PairPointerHead`
# design. A pre-T7 entset checkpoint's state_dict has no `actor.*` Linear
# weight at all any more, so without a dedicated version stamp it would fail
# with a raw `load_state_dict` key error instead of the honest "predates
# this change, use --fresh" refusal this project's checkpoint gate is
# supposed to give (ledger, round-2 gap 3). `ENTSET_HEAD_VERSION` is that
# stamp; these tests pin the refusal ahead of `check_checkpoint`'s shape
# check, so a stale head_version wins over a coincidentally-matching shape.


def _entset_ckpt(tmp_path, *, head_version=None):
    """A checkpoint_payload-shaped dict for a real combat entset model,
    optionally overriding/omitting `head_version` -- mirrors the schema-999
    monkeypatch fixture style (`test_make_model_refuses_future_v4_generation_schema`
    above): build the real thing via train_torch, then mutate the one field
    under test."""
    args = _combat_args(tmp_path, "entset")
    obs_dim = _combat_obs_dim()
    model = train_torch.make_model(args, obs_dim, COMBAT_N_ACTIONS)
    optimizer = torch.optim.Adam(model.parameters())
    ckpt = train_torch.checkpoint_payload(model, optimizer, 1, args, global_step=0)
    if head_version is None:
        del ckpt["head_version"]
    else:
        ckpt["head_version"] = head_version
    return ckpt, args, obs_dim


def test_check_checkpoint_refuses_entset_payload_missing_head_version(tmp_path):
    """Pre-stamp checkpoints (built before this field existed) carry no
    `head_version` key at all -- `check_checkpoint` must treat that as
    version 1 (the pre-T7 positional head) and refuse, naming both the
    stored (1) and required (models.ENTSET_HEAD_VERSION) versions plus
    --fresh."""
    ckpt, args, obs_dim = _entset_ckpt(tmp_path, head_version=None)
    with pytest.raises(SystemExit) as exc_info:
        train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)
    message = str(exc_info.value)
    assert "1" in message
    assert str(models.ENTSET_HEAD_VERSION) in message
    assert "--fresh" in message


def test_check_checkpoint_accepts_current_head_version(tmp_path):
    """A checkpoint stamped with head_version=4 (R9's pair-feature play
    head widening -- pinned as the literal ``models.ENTSET_HEAD_VERSION``
    is defined to be) passes. Deliberately hardcoded rather than read live
    off ``models.ENTSET_HEAD_VERSION``: reading the live constant on both
    the stamp and the check side would make this test pass under ANY value
    of the constant, including a regression that bumped it without meaning
    to -- pinning the literal is what actually catches that (see the
    report's mutation check: patching `ENTSET_HEAD_VERSION = 5` at runtime
    must turn this test red)."""
    ckpt, args, obs_dim = _entset_ckpt(tmp_path, head_version=4)
    train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)   # must not raise


def test_check_checkpoint_refuses_explicit_stale_head_version(tmp_path):
    """Not just a missing-key default -- an explicit `head_version=3` (R8's
    pointer-scored CHOICE/SELECT/belt-POTION structure, stamped once that
    field existed but before R9's pair-feature play-head widening) is
    refused too."""
    ckpt, args, obs_dim = _entset_ckpt(tmp_path, head_version=3)
    with pytest.raises(SystemExit):
        train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)


def test_check_checkpoint_head_version_refusal_wins_over_shape_mismatch(tmp_path):
    """A checkpoint that is doubly wrong -- stale head_version AND a shape
    tuple that no longer matches this run -- must fail on the honest
    head_version message, not the shape one: the shape check runs later in
    `check_checkpoint`, and a shape-only error would send someone chasing
    `--hidden` instead of the real cause."""
    ckpt, args, obs_dim = _entset_ckpt(tmp_path, head_version=None)
    ckpt["hidden"] = (999,)   # now also fails the (obs_dim, n_actions, hidden) shape check
    with pytest.raises(SystemExit) as exc_info:
        train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)
    message = str(exc_info.value)
    assert "head_version" in message or "predates" in message
    assert "(obs_dim, n_actions, hidden)" not in message


def test_check_checkpoint_entset_roundtrip_via_real_agent(tmp_path):
    """End-to-end per the brief: a freshly built entset agent's real
    `checkpoints.make_model` output, run through `train_torch.checkpoint_payload`
    and `check_checkpoint`, must be accepted -- importing train_torch has no
    heavy side effects (this file already does so at module scope for every
    other test above), so this uses the real function rather than
    replicating its dict literally."""
    args = _combat_args(tmp_path, "entset")
    obs_dim = _combat_obs_dim()
    model = checkpoints.make_model(train_torch.model_spec(args), obs_dim, COMBAT_N_ACTIONS)
    optimizer = torch.optim.Adam(model.parameters())
    ckpt = train_torch.checkpoint_payload(model, optimizer, 1, args, global_step=0)
    assert ckpt["head_version"] == models.ENTSET_HEAD_VERSION
    train_torch.check_checkpoint(ckpt, args, obs_dim, COMBAT_N_ACTIONS)   # must not raise


# ── R10: --shared-encoder ─────────────────────────────────────────────────
#
# `EntitySetActorCritic` builds TWO independent `_EntsetEncoder`s (actor +
# critic) -- every vocabulary table, every per-row projection, learned
# twice. `shared_encoder=True` (threaded from `--shared-encoder`) makes
# `self.actor_encoder is self.critic_encoder` ONE instance instead: the
# sharing granularity the controller decided on is "one shared encoder
# instance", not tables-only sharing (the fallback experiment nobody is
# running today). The two trunks (`self.actor`/`self.critic`) and every
# action head stay separate either way -- only the encoder is shared. The
# throughput/stability A/B itself is run by the controller, not here; this
# file only has to prove the flag builds the right graph and the checkpoint
# contract is honest about which arm a checkpoint was trained as.


def _combat_args_shared(tmp_path, *, shared_encoder: bool) -> Namespace:
    args = _combat_args(tmp_path, "entset")
    args.shared_encoder = shared_encoder
    return args


def test_shared_encoder_is_one_instance():
    """`shared_encoder=True` -> `actor_encoder is critic_encoder`, ONE
    encoder's worth of parameters, and the reduction versus the default
    (two independent encoders) equals EXACTLY one encoder's parameter
    count -- not "somewhat fewer", not "half, rounded" -- pins the sharing
    is a clean swap of one whole encoder object, nothing more, nothing
    less."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    separate = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))
    shared = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,),
        shared_encoder=True)

    assert shared.actor_encoder is shared.critic_encoder
    assert separate.actor_encoder is not separate.critic_encoder

    n_separate = sum(p.numel() for p in separate.parameters())
    n_shared = sum(p.numel() for p in shared.parameters())
    n_one_encoder = sum(p.numel() for p in separate.actor_encoder.parameters())
    assert n_one_encoder > 0, "fixture sanity: the encoder has parameters"
    assert n_shared < n_separate
    assert n_separate - n_shared == n_one_encoder

    # The shared encoder's own parameters must appear exactly ONCE in the
    # module's state_dict -- a plain `self.critic_encoder = self.actor_
    # encoder` would still register a SECOND "critic_encoder.*" copy of the
    # same tensors (nn.Module.__setattr__ registers by NAME, not identity).
    keys = list(shared.state_dict().keys())
    assert any(k.startswith("actor_encoder.") for k in keys)
    assert not any(k.startswith("critic_encoder.") for k in keys), (
        "critic_encoder must not be separately registered when shared -- "
        "found critic_encoder.* keys in state_dict() alongside "
        "actor_encoder.*, meaning the same encoder's weights are being "
        "saved twice under two names")


def test_default_is_separate():
    """Flag False (and the omitted default) must build two DISTINCT encoder
    instances -- guards the default arm staying byte-compatible with pre-R10
    behavior, the other half of the A/B this task exists to set up."""
    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    default_omitted = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,))
    default_explicit = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,),
        shared_encoder=False)

    for model in (default_omitted, default_explicit):
        assert model.actor_encoder is not model.critic_encoder
        keys = list(model.state_dict().keys())
        assert any(k.startswith("actor_encoder.") for k in keys)
        assert any(k.startswith("critic_encoder.") for k in keys)


def test_equivariance_holds_shared():
    """The hand-swap equivariance property (`test_tied_head_combat.py`'s
    `test_hand_swap_equivariance`) must still hold on a SHARED-encoder
    model: sharing the encoder object must not break the per-row pooling
    symmetry the play head's pointer scoring depends on. Reuses that file's
    fixture/helper functions (bare-module import -- `test/` shadows the
    stdlib `test` package, so `from test_tied_head_combat import ...` is the
    only import form that resolves to this repo's file, matching the
    existing `test_enemy_side_per_side.py` -> `test_hook_order` precedent)
    rather than re-deriving them, since duplicating hand-picked row-swap
    machinery would risk silently drifting from the real thing it's
    supposed to mirror."""
    from test_tied_head_combat import (
        MAX_ENEMIES,
        MAX_HAND,
        PLAY_BASE,
        POTION_BASE,
        _all_legal_mask,
        _copy_obs,
        _distinct_hand_pair,
        _reset_env,
        _swap_row,
        _to_tobs,
    )

    f_segments, i_segments = model_obs_layout(ModelSpec("combat", arch="entset"))
    model = EntitySetActorCritic(
        f_segments, i_segments, COMBAT_N_ACTIONS, COMBAT_LAYOUT, hidden=(32,),
        shared_encoder=True)
    assert model.actor_encoder is model.critic_encoder   # fixture sanity

    env, obs = _reset_env(seed=0)
    h1, h2 = _distinct_hand_pair(obs)

    layout_obs = combat_obs_layout()
    obs_b = _copy_obs(obs)
    _swap_row(obs_b["i"], layout_obs.i_slices["hand.ids"], MAX_HAND, h1, h2)
    _swap_row(obs_b["f"], layout_obs.f_slices["hand.f"], MAX_HAND, h1, h2)
    _swap_row(obs_b["f"], layout_obs.f_slices["damage_matrix"], MAX_HAND, h1, h2)

    mask_all = _all_legal_mask(COMBAT_N_ACTIONS)
    with torch.no_grad():
        logits_a = model.action_logits(_to_tobs(obs), mask_all)[0]
        logits_b = model.action_logits(_to_tobs(obs_b), mask_all)[0]

    atol = 5e-4   # same bound as test_hand_swap_equivariance -- see its
                  # docstring for the ctx-coupling residual this covers
    for e in range(MAX_ENEMIES):
        idx_h1 = PLAY_BASE + h1 * MAX_ENEMIES + e
        idx_h2 = PLAY_BASE + h2 * MAX_ENEMIES + e
        assert torch.allclose(logits_b[idx_h1], logits_a[idx_h2], atol=atol)
        assert torch.allclose(logits_b[idx_h2], logits_a[idx_h1], atol=atol)
    assert torch.allclose(logits_b[0], logits_a[0], atol=atol)
    assert torch.allclose(logits_b[POTION_BASE:], logits_a[POTION_BASE:], atol=atol)


def test_shared_encoder_checkpoint_roundtrips_and_rejects_mismatch(tmp_path):
    """Checkpoint honesty for the flag (mirrors the head_version tests
    above): a shared-arm checkpoint round-trips against a shared-arm run;
    a shared-saved/separate-requested checkpoint (and vice versa) is
    refused with a clear message naming --shared-encoder, BEFORE the
    (obs_dim, n_actions, hidden) shape fallback; and a checkpoint with no
    `shared_encoder` key at all (pre-R10) is treated as False, so it's
    accepted by a separate-arm request and refused by a shared-arm one."""
    obs_dim = _combat_obs_dim()

    shared_args = _combat_args_shared(tmp_path, shared_encoder=True)
    shared_model = checkpoints.make_model(
        train_torch.model_spec(shared_args), obs_dim, COMBAT_N_ACTIONS)
    optimizer = torch.optim.Adam(shared_model.parameters())
    shared_ckpt = train_torch.checkpoint_payload(
        shared_model, optimizer, 1, shared_args, global_step=0)
    assert shared_ckpt["shared_encoder"] is True

    # Round-trip: shared-saved, shared-requested.
    train_torch.check_checkpoint(shared_ckpt, shared_args, obs_dim, COMBAT_N_ACTIONS)

    separate_args = _combat_args_shared(tmp_path, shared_encoder=False)
    separate_model = checkpoints.make_model(
        train_torch.model_spec(separate_args), obs_dim, COMBAT_N_ACTIONS)
    optimizer2 = torch.optim.Adam(separate_model.parameters())
    separate_ckpt = train_torch.checkpoint_payload(
        separate_model, optimizer2, 1, separate_args, global_step=0)
    assert separate_ckpt["shared_encoder"] is False
    train_torch.check_checkpoint(separate_ckpt, separate_args, obs_dim, COMBAT_N_ACTIONS)

    # Mismatch: shared saved, separate requested.
    with pytest.raises(SystemExit, match="shared_encoder|shared-encoder"):
        train_torch.check_checkpoint(shared_ckpt, separate_args, obs_dim, COMBAT_N_ACTIONS)
    # Mismatch: separate saved, shared requested.
    with pytest.raises(SystemExit, match="shared_encoder|shared-encoder"):
        train_torch.check_checkpoint(separate_ckpt, shared_args, obs_dim, COMBAT_N_ACTIONS)

    # A doubly-wrong checkpoint (stale shared_encoder AND a bad shape) must
    # fail on the honest shared_encoder message, not the shape one -- same
    # "version gate wins over shape fallback" rule as head_version.
    doubly_wrong = dict(shared_ckpt)
    doubly_wrong["hidden"] = (999,)
    with pytest.raises(SystemExit) as exc_info:
        train_torch.check_checkpoint(doubly_wrong, separate_args, obs_dim, COMBAT_N_ACTIONS)
    message = str(exc_info.value)
    assert "shared_encoder" in message or "shared-encoder" in message
    assert "(obs_dim, n_actions, hidden)" not in message

    # Missing key (pre-R10 checkpoint) = False: accepted by a separate-arm
    # request, refused by a shared-arm one.
    legacy = dict(separate_ckpt)
    del legacy["shared_encoder"]
    train_torch.check_checkpoint(legacy, separate_args, obs_dim, COMBAT_N_ACTIONS)   # not raise
    with pytest.raises(SystemExit, match="shared_encoder|shared-encoder"):
        train_torch.check_checkpoint(legacy, shared_args, obs_dim, COMBAT_N_ACTIONS)

    # And the round-tripped model actually loads and matches the identity
    # property, not just the dict-level stamp.
    reloaded = checkpoints.make_model(
        train_torch.model_spec(shared_args), obs_dim, COMBAT_N_ACTIONS)
    reloaded.load_state_dict(shared_ckpt["model"])
    assert reloaded.actor_encoder is reloaded.critic_encoder


def test_make_model_builds_shared_arm_for_combat_and_run(tmp_path):
    """`make_model` threads `shared_encoder` for BOTH env families -- the
    combat env and the run-scale (run/column) envs share one code path
    through `checkpoints.make_model`, and R10 must not silently only wire
    one of them. Layout/tiling assertions confirm the shared flag doesn't
    perturb the action layout the encoder feeds -- sharing the encoder
    OBJECT must not change what rows/blocks it produces."""
    combat_obs_dim = _combat_obs_dim()
    combat_spec = ModelSpec("combat", arch="entset", hidden=(32,), shared_encoder=True)
    combat_model = checkpoints.make_model(combat_spec, combat_obs_dim, COMBAT_N_ACTIONS)
    assert combat_model.actor_encoder is combat_model.critic_encoder
    assert combat_model.action_layout.n_actions == COMBAT_N_ACTIONS

    run_f_segments, run_i_segments = model_obs_layout(ModelSpec("run", arch="entset"))
    run_obs_dim = (sum(w for _, w in run_f_segments), sum(w for _, w in run_i_segments))
    run_spec = ModelSpec("run", arch="entset", hidden=(32,), shared_encoder=True)
    run_model = checkpoints.make_model(run_spec, run_obs_dim, RUN_N_ACTIONS)
    assert run_model.actor_encoder is run_model.critic_encoder
    assert run_model.action_layout.n_actions == RUN_N_ACTIONS
    assert run_model.action_layout == RUN_LAYOUT, (
        "shared_encoder must not perturb the run action layout's tiling")

    column_spec = ModelSpec("column", arch="entset", hidden=(32,), shared_encoder=True)
    column_model = checkpoints.make_model(column_spec, run_obs_dim, RUN_N_ACTIONS)
    assert column_model.actor_encoder is column_model.critic_encoder

