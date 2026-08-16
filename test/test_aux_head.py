"""v10 aux head (spec 2026-08-13-aux-hp-head-gae-lambda-design):
module registration order, with_aux contract, lenient checkpoint load."""
from __future__ import annotations

import pytest
import torch

from sts2_rl import checkpoints, models
from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS
from sts2_rl.tensor_obs import TensorObs

# mirror test_warm_start.py's helpers to build a small run-kind entset agent
# and a dummy (obs, mask) batch -- reuse, don't reinvent.


def _spec() -> ModelSpec:
    return ModelSpec(env_kind="run", card_obs="hybrid", arch="entset",
                      hidden=(32,), shared_encoder=True)


def _build():
    spec = _spec()
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    model = make_model(spec, obs_dim, RUN_N_ACTIONS)
    return model, spec, obs_dim, RUN_N_ACTIONS


def _fake_ckpt(model, spec: ModelSpec, obs_dim, n_actions) -> dict:
    return {
        "model": model.state_dict(),
        "arch": spec.arch,
        "env_kind": spec.env_kind,
        "hidden": tuple(spec.hidden),
        "shared_encoder": spec.shared_encoder,
        "head_version": models.ENTSET_HEAD_VERSION,
        "obs_dim": obs_dim,
        "n_actions": n_actions,
        "obs_schema": checkpoints.obs_schema_version(spec),
    }


@pytest.fixture
def run_agent_factory():
    def _make():
        model, _spec_, _obs_dim, _n_actions = _build()
        return model
    return _make


@pytest.fixture
def run_agent(run_agent_factory):
    return run_agent_factory()


@pytest.fixture
def dummy_obs_mask():
    _model, _spec_, obs_dim, n_actions = _build()
    f_dim, i_dim = obs_dim
    batch = 4
    f = torch.zeros((batch, f_dim), dtype=torch.float32)
    i = torch.zeros((batch, i_dim), dtype=torch.int64)
    obs = TensorObs(f, i)
    mask = torch.ones((batch, n_actions), dtype=torch.bool)
    return obs, mask


def test_aux_head_params_registered_last(run_agent):
    names = [n for n, _ in run_agent.named_parameters()]
    first_aux = next(i for i, n in enumerate(names) if n.startswith("aux_"))
    assert all(n.startswith("aux_") for n in names[first_aux:])


def test_get_action_and_value_contracts(run_agent, dummy_obs_mask):
    obs, mask = dummy_obs_mask
    out4 = run_agent.get_action_and_value(obs, mask)
    assert len(out4) == 4                      # existing call sites untouched
    out5 = run_agent.get_action_and_value(obs, mask, with_aux=True)
    assert len(out5) == 5
    assert out5[4].shape == out5[3].shape      # aux pred shaped like value


def test_load_agent_accepts_pre_aux_checkpoint(tmp_path, run_agent_factory):
    # save a state_dict WITHOUT aux keys (an old checkpoint), reload
    agent = run_agent_factory()
    state = {k: v for k, v in agent.state_dict().items()
             if not k.startswith("aux_")}
    _model, spec, obs_dim, n_actions = _build()
    ckpt = _fake_ckpt(agent, spec, obs_dim, n_actions)
    ckpt["model"] = state
    path = tmp_path / "pre_aux.pt"
    torch.save(ckpt, path)

    model, loaded_ckpt = checkpoints.load_agent(
        str(path), env_kind=spec.env_kind, obs_dim=obs_dim,
        n_actions=n_actions, card_obs=spec.card_obs)

    aux_names = [n for n, _ in model.named_parameters() if n.startswith("aux_")]
    assert aux_names, "aux params should exist on the freshly-built model"
    assert loaded_ckpt is ckpt or loaded_ckpt["arch"] == spec.arch


def test_load_agent_still_rejects_non_aux_missing_keys(tmp_path, run_agent_factory):
    # same, but ALSO drop a critic key -> expect the load to raise as today.
    agent = run_agent_factory()
    state = {k: v for k, v in agent.state_dict().items()
             if not k.startswith("aux_")}
    critic_key = next(k for k in state if k.startswith("critic."))
    del state[critic_key]
    _model, spec, obs_dim, n_actions = _build()
    ckpt = _fake_ckpt(agent, spec, obs_dim, n_actions)
    ckpt["model"] = state
    path = tmp_path / "broken.pt"
    torch.save(ckpt, path)

    with pytest.raises(RuntimeError):
        checkpoints.load_agent(
            str(path), env_kind=spec.env_kind, obs_dim=obs_dim,
            n_actions=n_actions, card_obs=spec.card_obs)
