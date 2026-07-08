"""Torch policy/value networks for the STS2 combat env.

A deliberately plain **MLP baseline**: separate actor and critic trunks over the
flat ``Box`` observation, with an action-masked ``Discrete`` policy head. This is
the torso you train *first* — prove the env + PPO loop actually learn before
reaching for embeddings/attention (see the architecture discussion in RL.md).

When you upgrade, **only this file changes**: swap the one-hot ``Box`` input for
an ``neural_network.Embedding`` over card ids, or replace ``_mlp`` with a deep-set / attention
encoder over per-entity tokens. ``train_torch.py`` and the env stay put, because
the PPO loop only depends on the three methods below.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as neural_network
from torch.distributions import Categorical

# Illegal-action logit floor. Large enough that softmax gives ~0 probability,
# finite so log_prob / entropy never produce NaNs (the env guarantees at least
# one legal action per row, so a fully-masked row shouldn't occur anyway).
_MASK_FILL = -1e8


def _layer_init(layer: neural_network.Linear, std: float = np.sqrt(2), bias: float = 0.0) -> neural_network.Linear:
    """Orthogonal weight init with tuned gains — the standard PPO recipe, which
    matters a lot for stability. Hidden layers use gain ``sqrt(2)``; callers pass
    ``std=0.01`` for the policy head (near-uniform initial policy) and ``std=1.0``
    for the value head."""
    neural_network.init.orthogonal_(layer.weight, std)
    neural_network.init.constant_(layer.bias, bias)
    return layer


def _mlp(in_dim: int, hidden: tuple[int, ...], out_dim: int, out_std: float) -> neural_network.Sequential:
    layers: list[neural_network.Module] = []
    last = in_dim
    for h in hidden:
        layers += [_layer_init(neural_network.Linear(last, h)), neural_network.Tanh()]
        last = h
    layers.append(_layer_init(neural_network.Linear(last, out_dim), std=out_std))
    return neural_network.Sequential(*layers)


class MaskedActorCritic(neural_network.Module):
    """Separate-trunk actor/critic. The policy head is an action-masked
    categorical: illegal actions (from ``env.action_masks()``) are driven to ~0
    probability *before* sampling, so the distribution the agent acts under and
    the one the PPO update scores are identical."""

    def __init__(
        self,
        obs_dim: int,
        n_actions: int,
        hidden: tuple[int, ...] = (256, 256),
    ) -> None:
        super().__init__()
        self.obs_dim = obs_dim
        self.n_actions = n_actions
        self.hidden = tuple(hidden)
        self.actor = _mlp(obs_dim, self.hidden, n_actions, out_std=0.01)
        self.critic = _mlp(obs_dim, self.hidden, 1, out_std=1.0)

    def get_value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.critic(obs).squeeze(-1)

    def _dist(self, obs: torch.Tensor, mask: torch.Tensor) -> Categorical:
        logits = self.actor(obs)
        logits = logits.masked_fill(~mask, _MASK_FILL)
        return Categorical(logits=logits)

    def get_action_and_value(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        action: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns ``(action, log_prob, entropy, value)``. Pass ``action`` during
        the update to score stored actions; leave it ``None`` to sample fresh
        during rollout. ``mask`` is a boolean tensor, ``True`` = legal."""
        dist = self._dist(obs, mask)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.get_value(obs)
