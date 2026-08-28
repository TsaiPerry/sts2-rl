"""--critic-warmup freeze mechanism regression test.

The comment train_torch.py used to carry at the critic-only seam claimed
the actor's parameters are always disjoint from the critic's, so skipping
the policy/entropy terms during warmup left the actor untouched "for
free". That is false under `--arch entset --shared-encoder` (every live
checkpoint since v23): `EntitySetActorCritic.__init__` (models.py ~1086)
aliases `critic_encoder` to the SAME module object as `actor_encoder`
(`object.__setattr__`), so a value/aux backward pass during warmup
backprops through -- and moves -- the shared encoder the actor also
reads. `set_warmup_freeze(agent, frozen)` is the explicit fix: it toggles
`requires_grad` on the actor-path modules directly instead of relying on
disjointness.

This test builds a tiny CPU entset model the same way the trainer does
(`checkpoints.make_model` + a minimal `ModelSpec`), runs simulated
critic-only update steps THROUGH the real forward pass, and checks
bit-identity (`torch.equal`), not just `requires_grad` flags.
"""
from __future__ import annotations

import torch
from torch import nn

from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
from sts2_rl.run_env import N_ACTIONS as RUN_N_ACTIONS
from sts2_rl.tensor_obs import TensorObs


def _spec(shared_encoder: bool) -> ModelSpec:
    return ModelSpec(env_kind="run", card_obs="hybrid", arch="entset",
                      hidden=(32,), shared_encoder=shared_encoder)


def _build(shared_encoder: bool):
    spec = _spec(shared_encoder)
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    model = make_model(spec, obs_dim, RUN_N_ACTIONS)
    return model, obs_dim, RUN_N_ACTIONS


def _dummy_batch(obs_dim, n_actions, batch=4):
    f_dim, i_dim = obs_dim
    f = torch.randn((batch, f_dim), dtype=torch.float32)
    i = torch.zeros((batch, i_dim), dtype=torch.int64)
    obs = TensorObs(f, i)
    mask = torch.ones((batch, n_actions), dtype=torch.bool)
    return obs, mask


def _critic_only_step(model, optimizer, obs, mask, act):
    """One warmup-style update: value + aux losses on random targets,
    backward THROUGH the real forward -- the same shape of update
    train_torch.py's critic_only branch performs."""
    out = model.get_action_and_value(obs, mask, act, with_aux=True)
    _action, _logp, _entropy, newval, aux_pred, win_pred, turn_pred = out
    v_loss = ((newval - torch.randn_like(newval)) ** 2).mean()
    aux_loss = ((aux_pred - torch.randn_like(aux_pred)) ** 2).mean()
    win_loss = nn.functional.binary_cross_entropy_with_logits(
        win_pred, torch.rand_like(win_pred))
    turn_loss = ((turn_pred - torch.randn_like(turn_pred)) ** 2).mean()
    loss = v_loss + aux_loss + win_loss + turn_loss
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()


def _normal_step(model, optimizer, obs, mask, act):
    out = model.get_action_and_value(obs, mask, act)
    _action, logp, entropy, _value = out
    loss = -(logp.mean()) - 0.01 * entropy.mean()
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()


def _actor_path_names(model) -> set[str]:
    """Parameter names fed by the actor-path modules `set_warmup_freeze`
    must protect -- everything except critic/critic_q/aux tails."""
    protected_prefixes = ("critic", "aux_")
    return {n for n, _ in model.named_parameters()
            if not n.startswith(protected_prefixes)}


def test_set_warmup_freeze_shared_encoder_keeps_actor_bit_identical():
    import train_torch  # local import: keeps collection fast if unrelated tests fail to import

    model, obs_dim, n_actions = _build(shared_encoder=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2, eps=1e-5)
    obs, mask = _dummy_batch(obs_dim, n_actions)
    with torch.no_grad():
        action, *_ = model.get_action_and_value(obs, mask)

    snapshot = {n: p.detach().clone() for n, p in model.named_parameters()}
    actor_names = _actor_path_names(model)
    critic_names = {n for n, _ in model.named_parameters() if n.startswith("critic.")}
    assert actor_names and critic_names  # sanity: both sets non-empty

    train_torch.set_warmup_freeze(model, True)

    for _ in range(2):
        _critic_only_step(model, optimizer, obs, mask, action)

    # (a) every actor-path param is bit-identical to the snapshot.
    for n in actor_names:
        p = dict(model.named_parameters())[n]
        assert torch.equal(p, snapshot[n]), f"actor-path param {n} moved during frozen warmup"

    # (b) the critic head parameters changed.
    moved = [n for n in critic_names if not torch.equal(
        dict(model.named_parameters())[n], snapshot[n])]
    assert moved, "critic head should have trained during warmup"

    # (c) unfreezing restores requires_grad=True on every parameter.
    train_torch.set_warmup_freeze(model, False)
    assert all(p.requires_grad for p in model.parameters())

    # (d) the freeze is not sticky: a subsequent normal step moves the actor.
    post_unfreeze_snapshot = {n: p.detach().clone() for n, p in model.named_parameters()}
    _normal_step(model, optimizer, obs, mask, action)
    moved_actor = [n for n in actor_names if not torch.equal(
        dict(model.named_parameters())[n], post_unfreeze_snapshot[n])]
    assert moved_actor, "actor should train normally once warmup ends"


def test_set_warmup_freeze_unshared_encoder_leaves_critic_encoder_trainable():
    import train_torch

    model, obs_dim, n_actions = _build(shared_encoder=False)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2, eps=1e-5)
    obs, mask = _dummy_batch(obs_dim, n_actions)
    with torch.no_grad():
        action, *_ = model.get_action_and_value(obs, mask)

    snapshot = {n: p.detach().clone() for n, p in model.named_parameters()}

    train_torch.set_warmup_freeze(model, True)
    for _ in range(2):
        _critic_only_step(model, optimizer, obs, mask, action)

    # actor's OWN encoder stayed frozen bit-identical...
    actor_enc_names = [n for n, _ in model.named_parameters()
                       if n.startswith("actor_encoder.")]
    assert actor_enc_names
    for n in actor_enc_names:
        p = dict(model.named_parameters())[n]
        assert torch.equal(p, snapshot[n]), f"actor_encoder param {n} moved"

    # ...but the SEPARATE critic_encoder (not shared here) kept training.
    critic_enc_names = [n for n, _ in model.named_parameters()
                        if n.startswith("critic_encoder.")]
    assert critic_enc_names
    moved = [n for n in critic_enc_names if not torch.equal(
        dict(model.named_parameters())[n], snapshot[n])]
    assert moved, "unshared critic_encoder should stay trainable during warmup"

    train_torch.set_warmup_freeze(model, False)
    assert all(p.requires_grad for p in model.parameters())
