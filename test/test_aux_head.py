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


def _spec(n_quantiles: int = 0) -> ModelSpec:
    return ModelSpec(env_kind="run", card_obs="hybrid", arch="entset",
                      hidden=(32,), shared_encoder=True,
                      n_quantiles=n_quantiles)


def _build(n_quantiles: int = 0):
    spec = _spec(n_quantiles)
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


def _small_entset_fixture(n_quantiles: int = 0):
    """``(model, obs, mask)`` for a small run-kind entset agent -- the plain-
    function form of the ``run_agent``/``dummy_obs_mask`` fixture pair, for
    tests that want both without the fixture plumbing.

    ``n_quantiles`` (v26 distributional critic, plan
    2026-08-26-foresight-v25-v26) defaults to 0 = the scalar critic, so every
    pre-existing zero-arg call site is unchanged."""
    model, _spec_, obs_dim, n_actions = _build(n_quantiles)
    f_dim, i_dim = obs_dim
    batch = 4
    obs = TensorObs(torch.zeros((batch, f_dim), dtype=torch.float32),
                    torch.zeros((batch, i_dim), dtype=torch.int64))
    mask = torch.ones((batch, n_actions), dtype=torch.bool)
    return model, obs, mask


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
    # v25: with_aux appends THREE preds (hp3, win_logit, hpturn)
    out7 = run_agent.get_action_and_value(obs, mask, with_aux=True)
    assert len(out7) == 7
    for i in (4, 5, 6):
        assert out7[i].shape == out7[3].shape  # each aux pred shaped like value


def test_with_aux_appends_three_preds_and_dist_stays_final():
    model, obs, mask = _small_entset_fixture()
    out = model.get_action_and_value(obs, mask, with_aux=True, with_dist=True)
    assert len(out) == 8                        # 4 base + 3 aux + dist
    a_hp3, a_win, a_turn = out[4], out[5], out[6]
    assert a_hp3.shape == a_win.shape == a_turn.shape == out[3].shape
    from torch.distributions import Categorical
    assert isinstance(out[7], Categorical)


def test_new_aux_heads_registered_after_hp3():
    model, _, _ = _small_entset_fixture()
    names = [n for n, _ in model.named_parameters()]
    i_hp3 = max(i for i, n in enumerate(names) if n.startswith("aux_hp3_head"))
    i_win = min(i for i, n in enumerate(names) if n.startswith("aux_win_head"))
    i_turn = min(i for i, n in enumerate(names) if n.startswith("aux_hpturn_head"))
    assert i_hp3 < i_win < i_turn               # positional-Adam tail rule


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


def _trimmed_adam_state(model, n_drop: int) -> dict:
    """Adam state for `model` minus its last `n_drop` params — i.e. what a
    checkpoint saved before those tail params existed looks like."""
    params = list(model.parameters())
    opt = torch.optim.Adam(params[:len(params) - n_drop], lr=3e-4, eps=1e-5)
    for p in opt.param_groups[0]["params"]:
        # NONZERO on purpose: a zero grad leaves exp_avg all-zeros, which the
        # "the saved moments survived the patch" assertion could not tell from
        # a freshly-initialised (also all-zeros) state.
        p.grad = torch.full_like(p, 0.1)
    opt.step()                                   # populate exp_avg/exp_avg_sq
    return opt.state_dict()


@pytest.mark.parametrize("n_drop", [8, 12])
def test_optimizer_group_patch_admits_a_pre_v25_checkpoint(n_drop):
    """v25 smoke regression (2026-08-26): resuming v23_s26 (which HAS the v10
    aux_hp3 head) blew up in Adam.load_state_dict because the patch sized the
    fresh tail by counting EVERY aux_* param instead of the missing ones.

    n_drop=8 is the real v23->v25 case (aux_win + aux_hpturn); n_drop=12 is a
    pre-v10 checkpoint (all three heads fresh), which used to work and must
    keep working.
    """
    import train_torch

    model, _, _ = _small_entset_fixture()
    params = list(model.parameters())
    n_live = len(params)
    opt_state = _trimmed_adam_state(model, n_drop)
    assert len(opt_state["param_groups"][0]["params"]) == n_live - n_drop
    saved_exp_avg = opt_state["state"][0]["exp_avg"].clone()
    assert saved_exp_avg.abs().sum() > 0     # the fixture really banked moments

    assert train_torch.patch_optimizer_group_for_fresh_aux(
        opt_state, n_live, n_drop) is True
    assert opt_state["param_groups"][0]["params"] == list(range(n_live))

    # the real assertion: Adam over the FULL live model now accepts it
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4, eps=1e-5)
    optimizer.load_state_dict(opt_state)
    assert len(optimizer.param_groups[0]["params"]) == n_live

    # (a) the patch widened the group WITHOUT disturbing what was saved: a
    # pre-existing param's Adam moments come back verbatim, so the resumed
    # run keeps its optimizer history instead of restarting it.
    torch.testing.assert_close(optimizer.state[params[0]]["exp_avg"],
                               saved_exp_avg)
    # (b) the fresh tail params carry NO state — Adam initialises them lazily
    # on the first step, which is exactly what a brand-new head wants.
    for p in params[n_live - n_drop:]:
        assert not optimizer.state.get(p), "fresh tail param must start stateless"


def test_optimizer_group_patch_declines_when_nothing_is_fresh():
    import train_torch

    model, _, _ = _small_entset_fixture()
    n_live = sum(1 for _ in model.parameters())
    opt_state = _trimmed_adam_state(model, 0)

    # a current checkpoint: no fresh params, nothing to patch
    assert train_torch.patch_optimizer_group_for_fresh_aux(
        opt_state, n_live, 0) is False
    # a size mismatch the aux tail does NOT explain stays unpatched (and so
    # still raises inside load_state_dict, as it should)
    short = _trimmed_adam_state(model, 8)
    assert train_torch.patch_optimizer_group_for_fresh_aux(
        short, n_live, 3) is False
