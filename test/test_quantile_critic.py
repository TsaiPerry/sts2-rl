"""test/test_quantile_critic.py — Phase 2 of 2026-08-26-foresight plan.

The `n_quantiles` distributional critic: tail registration order, the
`with_quantiles` tuple contract, `get_value` == quantile mean, the
scalar-critic default staying bit-identical, the checkpoint stamp/refusal,
and the scalar->quantile lenient load that fresh-inits `critic_q`.
"""
import pytest
import torch

from sts2_rl import checkpoints, models
from test_aux_head import _build, _fake_ckpt, _small_entset_fixture


def test_get_value_is_quantile_mean():
    model, obs, mask = _small_entset_fixture(n_quantiles=8)
    out = model.get_action_and_value(obs, mask, with_quantiles=True)
    q = out[-1]
    assert q.shape[-1] == 8
    torch.testing.assert_close(model.get_value(obs), q.mean(-1))


def test_scalar_default_unchanged():
    model, obs, _ = _small_entset_fixture()          # n_quantiles=0
    assert not hasattr(model, "critic_q")
    assert model.get_value(obs).dim() == 1


def test_quantile_huber_pinball_ordering():
    # A correct QR loss is minimized (in expectation) by the true quantiles:
    # against targets ~U{0,1}, predicting the true deciles must score
    # strictly better than predicting all-zeros.
    from train_torch import quantile_huber_loss
    torch.manual_seed(0)
    target = torch.randint(0, 2, (4096,)).float()
    taus = (2 * torch.arange(8) + 1) / 16.0
    good = torch.quantile(target, taus).expand(4096, 8)
    bad = torch.zeros(4096, 8)
    assert quantile_huber_loss(good, target) < quantile_huber_loss(bad, target)


# ── tail order / tuple contract ──────────────────────────────────────────

def test_critic_q_is_registered_after_the_aux_tail():
    """FROZEN tail order aux_hp3, aux_win, aux_hpturn, critic_q — Adam state
    is positional and the lenient load fresh-inits exactly the tail."""
    model, _, _ = _small_entset_fixture(n_quantiles=8)
    names = [n for n, _ in model.named_parameters()]
    i_turn = max(i for i, n in enumerate(names) if n.startswith("aux_hpturn_head"))
    i_q = min(i for i, n in enumerate(names) if n.startswith("critic_q"))
    assert i_turn < i_q
    assert all(n.startswith("critic_q") for n in names[i_q:])


def test_with_quantiles_sits_between_aux_and_dist():
    model, obs, mask = _small_entset_fixture(n_quantiles=8)
    out = model.get_action_and_value(
        obs, mask, with_aux=True, with_quantiles=True, with_dist=True)
    assert len(out) == 9                    # 4 base + 3 aux + quantiles + dist
    assert out[7].shape == (obs.f.shape[0], 8)
    from torch.distributions import Categorical
    assert isinstance(out[8], Categorical)


def test_value_element_is_the_quantile_mean_too():
    """out[3] must be the quantile mean, not the (untrained, gradient-free)
    scalar critic — the rollout's GAE reads it."""
    model, obs, mask = _small_entset_fixture(n_quantiles=8)
    out = model.get_action_and_value(obs, mask, with_quantiles=True)
    torch.testing.assert_close(out[3], out[-1].mean(-1))


def test_scalar_critic_gets_no_gradient_when_quantile_is_on():
    model, obs, mask = _small_entset_fixture(n_quantiles=8)
    out = model.get_action_and_value(obs, mask, with_quantiles=True)
    out[-1].sum().backward()
    assert all(p.grad is None for p in model.critic.parameters())
    assert any(p.grad is not None for p in model.critic_q.parameters())


def test_with_quantiles_on_a_scalar_model_raises():
    model, obs, mask = _small_entset_fixture()
    with pytest.raises(ValueError):
        model.get_action_and_value(obs, mask, with_quantiles=True)


# ── checkpoint stamp / refusal / lenient load ────────────────────────────

def test_check_checkpoint_refuses_n_quantiles_mismatch():
    model, spec, obs_dim, n_actions = _build(n_quantiles=8)
    ckpt = _fake_ckpt(model, spec, obs_dim, n_actions)
    ckpt["n_quantiles"] = 8
    checkpoints.check_checkpoint(ckpt, spec, obs_dim, n_actions)   # must not raise

    scalar_spec = checkpoints.ModelSpec(
        env_kind=spec.env_kind, card_obs=spec.card_obs, arch=spec.arch,
        hidden=spec.hidden, shared_encoder=spec.shared_encoder)
    assert scalar_spec.n_quantiles == 0
    with pytest.raises(SystemExit, match="n_quantiles"):
        checkpoints.check_checkpoint(ckpt, scalar_spec, obs_dim, n_actions)
    # ...and the reverse: an unstamped (pre-quantile) checkpoint against a
    # quantile spec.
    del ckpt["n_quantiles"]
    with pytest.raises(SystemExit, match="n_quantiles"):
        checkpoints.check_checkpoint(ckpt, spec, obs_dim, n_actions)


def test_lenient_load_fresh_inits_critic_q_from_a_scalar_checkpoint():
    scalar, _, _, _ = _build()
    quantile, _, _, _ = _build(n_quantiles=8)
    n_fresh = checkpoints.load_model_state_lenient(quantile, scalar.state_dict())
    # exactly critic_q's own params were missing (aux tail is present in both)
    critic_q_keys = [k for k in quantile.state_dict() if k.startswith("critic_q")]
    assert n_fresh == len(critic_q_keys) > 0
    # everything else loaded strictly
    torch.testing.assert_close(quantile.critic[0].weight, scalar.critic[0].weight)
    torch.testing.assert_close(
        quantile.aux_hpturn_head[0].weight, scalar.aux_hpturn_head[0].weight)


def test_optimizer_group_patch_sizes_a_scalar_to_quantile_resume():
    """The fresh-tail count from the lenient load must be exactly what
    patch_optimizer_group_for_fresh_aux needs to widen a saved Adam group."""
    import train_torch

    scalar, _, _, _ = _build()
    quantile, _, _, _ = _build(n_quantiles=8)
    n_fresh = checkpoints.load_model_state_lenient(quantile, scalar.state_dict())
    n_live = sum(1 for _ in quantile.parameters())

    params = list(quantile.parameters())
    opt = torch.optim.Adam(params[:n_live - n_fresh], lr=3e-4, eps=1e-5)
    for p in opt.param_groups[0]["params"]:
        p.grad = torch.zeros_like(p)
    opt.step()
    opt_state = opt.state_dict()

    assert train_torch.patch_optimizer_group_for_fresh_aux(
        opt_state, n_live, n_fresh) is True
    full = torch.optim.Adam(quantile.parameters(), lr=3e-4, eps=1e-5)
    full.load_state_dict(opt_state)
    assert len(full.param_groups[0]["params"]) == n_live


def test_checkpoint_payload_stamps_n_quantiles(tmp_path):
    import argparse

    import train_torch

    model, spec, obs_dim, n_actions = _build(n_quantiles=8)
    args = argparse.Namespace(
        arch=spec.arch, env=spec.env_kind, card_obs=spec.card_obs,
        hidden=list(spec.hidden), shared_encoder=spec.shared_encoder,
        n_envs=1, n_steps=1, quantile_critic=8)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4, eps=1e-5)
    payload = train_torch.checkpoint_payload(model, optimizer, 1, args, 0)
    assert payload["n_quantiles"] == 8
    assert train_torch.model_spec(args).n_quantiles == 8


def test_head_version_is_untouched_by_the_quantile_critic():
    """n_quantiles is its own stamp (orthogonal to head structure), so the
    entset head version must NOT move for it."""
    assert models.ENTSET_HEAD_VERSION == 5
