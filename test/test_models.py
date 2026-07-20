"""Tests for the entity/embedding actor-critic (sts2_rl/models.py) and the
train_torch checkpoint arch stamping.

The entity model consumes the flat Box obs unchanged (strategy (a) of
prompts/embedding-model.md): it slices the observation by the env's named
segment layout and encodes vocabulary segments through shared embedding
tables sized to the frozen vocab capacities (vocab.py), so porting content
appends rows and never reshapes weights.
"""
from __future__ import annotations

import random
from argparse import Namespace

import pytest
import torch

import train_torch
from sts2_rl.full_env import obs_segments
from sts2_rl.models import EntityActorCritic, MaskedActorCritic
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS
from sts2_rl.run_env import run_obs_segments
from sts2_rl.vocab import CAPACITIES

COMBAT_N_ACTIONS = 79


def combat_segments() -> list[tuple[str, int]]:
    return obs_segments("hybrid")


def composed_run_segments() -> list[tuple[str, int]]:
    """The run-env layout the trainer hands the model: run segments plus the
    combat block expanded into its own named segments."""
    return run_obs_segments("hybrid") + [
        (f"combat.{name}", width) for name, width in obs_segments("hybrid")
    ]


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


def test_embedding_tables_sized_to_capacities():
    # The run layout touches every vocabulary kind.
    model = make_entity(composed_run_segments(), n_actions=RUN_N_ACTIONS)
    for enc in (model.actor_encoder, model.critic_encoder):
        for kind in ("cards", "relics", "powers", "monsters", "potions",
                     "events", "purposes"):
            assert enc.tables[kind].shape[0] == CAPACITIES[kind], kind
        # Base/upgraded modifier rows for the 2×N_CARDS histograms.
        assert enc.tables["card_upgrade"].shape[0] == 2


def test_run_layout_builds_and_runs():
    segs = composed_run_segments()
    model = make_entity(segs, n_actions=RUN_N_ACTIONS)
    assert model.obs_dim == sum(w for _, w in segs)
    obs, mask = rand_obs_mask(model, batch=3, seed=3)
    action, logp, entropy, value = model.get_action_and_value(obs, mask)
    assert action.shape == (3,)
    assert value.shape == (3,)


def test_entity_strictly_smaller_than_mlp():
    obs_dim = sum(w for _, w in combat_segments())
    mlp = MaskedActorCritic(obs_dim, COMBAT_N_ACTIONS)          # default 256x256
    entity = EntityActorCritic(combat_segments(), COMBAT_N_ACTIONS)
    n_mlp = sum(p.numel() for p in mlp.parameters())
    n_entity = sum(p.numel() for p in entity.parameters())
    assert n_entity < n_mlp


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


def _combat_args(tmp_path, arch: str) -> Namespace:
    return Namespace(
        env="combat", arch=arch, card_obs="hybrid",
        hidden=[32], save=str(tmp_path / "ckpt.pt"),
        n_envs=train_torch.DEFAULT_N_ENVS, n_steps=train_torch.DEFAULT_N_STEPS,
    )


def test_make_model_factory(tmp_path):
    obs_dim = sum(w for _, w in combat_segments())
    mlp = train_torch.make_model(
        _combat_args(tmp_path, "mlp"), obs_dim, COMBAT_N_ACTIONS)
    assert isinstance(mlp, MaskedActorCritic)
    entity = train_torch.make_model(
        _combat_args(tmp_path, "entity"), obs_dim, COMBAT_N_ACTIONS)
    assert isinstance(entity, EntityActorCritic)
    assert entity.obs_dim == obs_dim


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
