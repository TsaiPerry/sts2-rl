"""Torch policy/value networks for the STS2 combat env.

Two architectures, selected by ``train_torch.py --arch``:

* ``MaskedActorCritic`` (``--arch mlp``) — the plain MLP baseline: separate
  actor and critic trunks straight over the flat ``Box`` observation.
* ``EntityActorCritic`` (``--arch entity``) — same trunks/heads, but the flat
  observation is first passed through a per-segment encoder
  (``_SegmentEncoder``) that replaces every sparse vocabulary segment
  (card/relic/power/monster/potion/event/purpose one-hots and histograms)
  with a low-dimensional embedding, sharing one table per vocabulary kind
  across all segments that reference it. A one-hot segment × embedding table
  is a bias-free ``Linear`` over that slice, so this works on the existing
  float obs — including multi-hot histograms, where it becomes a sum of
  embeddings (exactly the right set pooling). Envs and the PPO loop are
  untouched (strategy (a) of prompts/embedding-model.md); tables are sized to
  the frozen vocab *capacities* (vocab.py), so porting content appends rows
  and never reshapes weights.

``train_torch.py`` and the env stay put when architectures change, because the
PPO loop only depends on ``get_value`` / ``get_action_and_value``.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as neural_network
from torch.distributions import Categorical

from .vocab import CAPACITIES

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


# ── Entity/embedding architecture ────────────────────────────────────────────

N_CARDS = CAPACITIES["cards"]
N_RELICS = CAPACITIES["relics"]
N_POWERS = CAPACITIES["powers"]
N_MONSTERS = CAPACITIES["monsters"]
N_POTIONS = CAPACITIES["potions"]
N_EVENTS = CAPACITIES["events"]
N_PURPOSES = CAPACITIES["purposes"]

# Embedding width per vocabulary kind (table rows are always the capacity).
EMBED_DIMS: dict[str, int] = {
    "cards": 32,
    "relics": 16,
    "powers": 16,
    "monsters": 16,
    "potions": 8,
    "events": 8,
    "purposes": 4,
}


def _segment_plan(name: str, width: int) -> list[tuple[str, int]]:
    """Split one named obs segment into (piece kind, piece width) parts.

    Piece kinds are vocabulary names (encoded through the shared table),
    ``cards2`` (a base/upgraded ``2 × N_CARDS`` histogram), or ``raw``
    (passed through unencoded). Matching is on the segment's name suffix
    (so ``combat.``-prefixed run-env segments classify identically) with the
    width as a cross-check — anything unrecognized stays raw.
    """
    last = name.rsplit(".", 1)[-1]
    if last == "onehot" and width == N_CARDS:
        return [("cards", width)]
    if last == "powers" and width == 3 * N_POWERS:
        return [("powers", width)]
    if last == "identity" and width == N_MONSTERS:
        return [("monsters", width)]
    if last == "identity" and width == N_EVENTS:
        return [("events", width)]
    if width == 2 * N_CARDS:   # pile/deck/select-candidate histograms
        return [("cards2", width)]
    if last == "relics" and width == N_RELICS:
        return [("relics", width)]
    if last == "purpose" and width == N_PURPOSES:
        return [("purposes", width)]
    # Slot rows: [present, one-hot, trailing scalars] (combat/run/shop/reward
    # potion rows, shop/reward card rows, shop relic rows).
    for prefix, kind, n in (("potion", "potions", N_POTIONS),
                            ("card", "cards", N_CARDS),
                            ("relic", "relics", N_RELICS)):
        if last.startswith(prefix) and 0 <= width - 1 - n <= 3:
            tail = width - 1 - n
            return [("raw", 1), (kind, n)] + ([("raw", tail)] if tail else [])
    return [("raw", width)]


class _SegmentEncoder(neural_network.Module):
    """Encodes the flat obs into a dense feature vector, segment by segment.

    Vocabulary pieces multiply into shared per-kind embedding tables (row ``i``
    = frozen vocab id ``i`` forever, ``num rows`` = the reserved capacity);
    raw pieces pass through unchanged, in layout order.
    """

    def __init__(self, segments: list[tuple[str, int]],
                 embed_dims: dict[str, int] | None = None) -> None:
        super().__init__()
        dims = dict(EMBED_DIMS, **(embed_dims or {}))
        self.tables = neural_network.ParameterDict()
        rows = {"cards": N_CARDS, "relics": N_RELICS, "monsters": N_MONSTERS,
                "potions": N_POTIONS, "events": N_EVENTS, "purposes": N_PURPOSES}

        def table(kind: str) -> torch.nn.Parameter:
            if kind not in self.tables:
                if kind == "powers":
                    # Three rows per power id: presence, fine amount, coarse
                    # amount — matching the (pres, ±10, ±50) obs triples.
                    w = torch.empty(N_POWERS, 3, dims["powers"])
                    neural_network.init.orthogonal_(w.view(3 * N_POWERS, dims["powers"]), np.sqrt(2))
                elif kind == "card_upgrade":
                    # Base/upgraded modifier rows added onto the card table.
                    w = torch.empty(2, dims["cards"])
                    neural_network.init.orthogonal_(w, np.sqrt(2))
                else:
                    w = torch.empty(rows[kind], dims[kind])
                    neural_network.init.orthogonal_(w, np.sqrt(2))
                self.tables[kind] = neural_network.Parameter(w)
            return self.tables[kind]

        # (kind, start, stop) in layout order; out_dim accumulates as we go.
        self._plan: list[tuple[str, int, int]] = []
        self.out_dim = 0
        offset = 0
        for name, width in segments:
            for kind, w in _segment_plan(name, width):
                self._plan.append((kind, offset, offset + w))
                offset += w
                if kind == "raw":
                    self.out_dim += w
                else:
                    table("cards" if kind == "cards2" else kind)
                    if kind == "cards2":
                        table("card_upgrade")
                    self.out_dim += dims["cards" if kind == "cards2" else kind]
        self.in_dim = offset

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        parts: list[torch.Tensor] = []
        for kind, start, stop in self._plan:
            x = obs[..., start:stop]
            if kind == "raw":
                parts.append(x)
            elif kind == "powers":
                xv = x.reshape(*x.shape[:-1], N_POWERS, 3)
                parts.append(torch.einsum("...pc,pcd->...d", xv, self.tables["powers"]))
            elif kind == "cards2":
                base, upg = x[..., :N_CARDS], x[..., N_CARDS:]
                h = (base + upg) @ self.tables["cards"]
                totals = torch.stack((base.sum(-1), upg.sum(-1)), dim=-1)
                parts.append(h + totals @ self.tables["card_upgrade"])
            else:
                parts.append(x @ self.tables[kind])
        return torch.cat(parts, dim=-1)


class EntityActorCritic(neural_network.Module):
    """Embedding/entity actor-critic over the *unchanged* flat observation.

    Same masked-categorical policy contract as ``MaskedActorCritic``; the only
    difference is a ``_SegmentEncoder`` in front of each trunk (actor and
    critic stay fully separate, encoders included, mirroring the baseline's
    separate-trunk design). Constructed from the env's self-described layout:
    pass ``obs_segments()`` (for the run-scale envs, with the combat block
    expanded — see ``train_torch.env_obs_segments``).
    """

    arch = "entity"

    def __init__(
        self,
        segments: list[tuple[str, int]],
        n_actions: int,
        hidden: tuple[int, ...] = (256, 256),
        embed_dims: dict[str, int] | None = None,
    ) -> None:
        super().__init__()
        self.segments = list(segments)
        self.obs_dim = sum(w for _, w in segments)
        self.n_actions = n_actions
        self.hidden = tuple(hidden)
        self.actor_encoder = _SegmentEncoder(segments, embed_dims)
        self.critic_encoder = _SegmentEncoder(segments, embed_dims)
        self.actor = _mlp(self.actor_encoder.out_dim, self.hidden, n_actions, out_std=0.01)
        self.critic = _mlp(self.critic_encoder.out_dim, self.hidden, 1, out_std=1.0)

    def get_value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.critic(self.critic_encoder(obs)).squeeze(-1)

    def _dist(self, obs: torch.Tensor, mask: torch.Tensor) -> Categorical:
        logits = self.actor(self.actor_encoder(obs))
        logits = logits.masked_fill(~mask, _MASK_FILL)
        return Categorical(logits=logits)

    def get_action_and_value(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        action: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns ``(action, log_prob, entropy, value)`` — same contract as
        ``MaskedActorCritic.get_action_and_value``."""
        dist = self._dist(obs, mask)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.get_value(obs)
