"""v16: potion-head exploration bonus — unit tests for the loss helper
and the with_dist plumbing. The helper is a pure function so the math
is testable without a training loop."""
import math

import pytest
import torch

from sts2_rl.full_env import COMBAT_POTION_BASE, MAX_ENEMIES
from sts2_rl.run_env import MAX_POTION_SLOTS, N_ACTIONS, POTION_BASE
import train_torch


def _mask(legal_indices):
    m = torch.zeros(1, N_ACTIONS, dtype=torch.bool)
    m[0, list(legal_indices)] = True
    return m


def _uniform_probs(mask):
    logits = torch.full(mask.shape, -1e8).masked_fill(mask, 0.0)
    return logits.softmax(-1)


def test_no_legal_potion_action_contributes_zero():
    mask = _mask([0, 1, 2])          # END_TURN + two plays, no potions
    probs = _uniform_probs(mask)
    assert train_torch.potion_entropy_bonus(probs, mask).item() == 0.0


def test_binary_entropy_of_combat_potion_mass():
    # 2 legal actions: END_TURN and one combat potion throw -> uniform
    # probs put q = 0.5 on potion mass -> H_b(0.5) = ln 2.
    mask = _mask([0, COMBAT_POTION_BASE])
    probs = _uniform_probs(mask)
    bonus = train_torch.potion_entropy_bonus(probs, mask)
    assert bonus.item() == pytest.approx(math.log(2), abs=1e-4)


def test_belt_block_counts_too():
    mask = _mask([POTION_BASE + 3, POTION_BASE + 4])   # only belt drinks
    probs = _uniform_probs(mask)                        # q = 1.0 -> clamped
    bonus = train_torch.potion_entropy_bonus(probs, mask)
    assert 0.0 < bonus.item() < 1e-3                    # H_b(1-eps) ~ 0


def test_mean_is_over_potion_steps_only():
    # Row 0 has a potion action (q=0.5 -> ln 2); row 1 has none (0,
    # excluded from the mean, not averaged in as a zero).
    m0, m1 = _mask([0, COMBAT_POTION_BASE]), _mask([0, 1])
    mask = torch.cat([m0, m1])
    probs = torch.cat([_uniform_probs(m0), _uniform_probs(m1)])
    bonus = train_torch.potion_entropy_bonus(probs, mask)
    assert bonus.item() == pytest.approx(math.log(2), abs=1e-4)


def test_with_dist_returns_the_categorical():
    # Mirrors test_aux_head.py's _build() helper: real make_model(spec,
    # obs_dim, n_actions) signature + model_obs_layout-derived obs_dim,
    # for a run-kind entset agent. Obs batching mirrors
    # test_tied_head_combat.py's _to_tobs (TensorObs.from_dict(...)[None]).
    from sts2_rl.checkpoints import ModelSpec, make_model, model_obs_layout
    from sts2_rl.run_env import STS2RunEnv
    from sts2_rl.tensor_obs import TensorObs

    spec = ModelSpec(env_kind="run", card_obs="hybrid", arch="entset",
                      hidden=(32,), shared_encoder=True)
    f_segs, i_segs = model_obs_layout(spec)
    obs_dim = (sum(w for _, w in f_segs), sum(w for _, w in i_segs))
    agent = make_model(spec, obs_dim, N_ACTIONS)

    env = STS2RunEnv()
    obs, _info = env.reset(seed=0)
    mask = torch.as_tensor(env.action_masks(), dtype=torch.bool).unsqueeze(0)
    tobs = TensorObs.from_dict(obs, device="cpu")[None]

    out = agent.get_action_and_value(tobs, mask, with_dist=True)
    dist = out[-1]
    assert isinstance(dist, torch.distributions.Categorical)
    assert torch.allclose(dist.probs.sum(-1), torch.ones(1))
