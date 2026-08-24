"""Torch policy/value networks for the STS2 combat env.

Three architectures, selected by ``train_torch.py --arch``:

* ``MaskedActorCritic`` (``--arch mlp``) — the plain MLP baseline: separate
  actor and critic trunks straight over a flat observation.
* ``EntityActorCritic`` (``--arch entity``) — same trunks/heads, but the flat
  observation is first passed through a per-segment encoder
  (``_SegmentEncoder``) that replaces every sparse vocabulary segment
  (card/relic/power/monster/potion/event/purpose one-hots and histograms)
  with a low-dimensional embedding, sharing one table per vocabulary kind
  across all segments that reference it. A one-hot segment × embedding table
  is a bias-free ``Linear`` over that slice, so this works on a flat float
  obs — including multi-hot histograms, where it becomes a sum of embeddings
  (exactly the right set pooling). Tables are sized to the frozen vocab
  *capacities* (vocab.py), so porting content appends rows and never
  reshapes weights. Frozen at the v3-era flat-``Box`` obs schema — see the
  next arch for the schema-v4 replacement.
* ``EntitySetActorCritic`` (``--arch entset``, "entity-set") — the v4
  ``{"f", "i"}`` observation's own architecture (OBS_SCHEMA.md §2.2): a
  masked sum-pool of per-row embeddings over each ``.ids`` block, using the
  id/float pair directly rather than a flat-obs slice. ``mlp``/``entity``
  still work against the new envs — they just see a flattened ``concat(f,
  i)`` with ids as plain numbers, no embedding, which is a deliberate
  degeneration, not a bug: they are the frozen v3-era archs, and ``entset``
  is the schema-v4 replacement.

``train_torch.py`` and the env stay put when architectures change, because the
PPO loop only depends on ``get_value`` / ``get_action_and_value``. Those two
methods accept either a plain flat ``torch.Tensor`` (the historical contract,
still used directly by unit tests) or a
:class:`~sts2_rl.tensor_obs.TensorObs` (what the real training loop now
passes uniformly, regardless of arch) — ``mlp``/``entity`` flatten the
latter via ``_as_flat``; ``entset`` consumes it directly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as neural_network
import torch.nn.functional as neural_functional
from torch.distributions import Categorical

from .full_env import MAX_ENEMIES, MAX_HAND, combat_action_count
from .tensor_obs import TensorObs
from .vocab import CAPACITIES

# Illegal-action logit floor. Large enough that softmax gives ~0 probability,
# finite so log_prob / entropy never produce NaNs (the env guarantees at least
# one legal action per row, so a fully-masked row shouldn't occur anyway).
_MASK_FILL = -1e8


def _as_flat(obs: torch.Tensor | TensorObs) -> torch.Tensor:
    """``mlp``/``entity`` keep the pre-v4 flat-tensor contract, so a
    :class:`TensorObs` (what the real training loop passes uniformly) is
    flattened to ``concat(f, i.float())`` before it reaches either
    architecture's first ``Linear``. A plain ``torch.Tensor`` (every direct
    unit-test call site) passes straight through unchanged. Deliberate
    degeneration, not a bug: ids become plain numbers with no embedding,
    because ``mlp``/``entity`` are the frozen v3-era archs and ``entset`` is
    the schema-v4 replacement (see the module docstring)."""
    if isinstance(obs, TensorObs):
        return torch.cat([obs.f, obs.i.to(obs.f.dtype)], dim=-1)
    return obs


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


def _trunk(in_dim: int, hidden: tuple[int, ...]) -> neural_network.Sequential:
    """Like ``_mlp`` but with no final output layer -- a pure FEATURE trunk
    (``Linear -> Tanh`` per hidden width, orthogonal init) whose output is a
    ``hidden[-1]``-wide context vector for downstream heads to consume,
    rather than logits itself. Used by ``EntitySetActorCritic``'s tied
    action head: several heads read this same ``ctx`` instead of one final
    ``Linear(hidden[-1], n_actions)``."""
    layers: list[neural_network.Module] = []
    last = in_dim
    for h in hidden:
        layers += [_layer_init(neural_network.Linear(last, h)), neural_network.Tanh()]
        last = h
    return neural_network.Sequential(*layers)


class MaskedActorCritic(neural_network.Module):
    """Separate-trunk actor/critic. The policy head is an action-masked
    categorical: illegal actions (from ``env.action_masks()``) are driven to ~0
    probability *before* sampling, so the distribution the agent acts under and
    the one the PPO update scores are identical."""

    arch = "mlp"

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

    def get_value(self, obs: torch.Tensor | TensorObs) -> torch.Tensor:
        return self.critic(_as_flat(obs)).squeeze(-1)

    def action_logits(self, obs: torch.Tensor | TensorObs, mask: torch.Tensor) -> torch.Tensor:
        """Policy logits with illegal actions driven to ~0 probability — the
        distribution the agent acts under. ``argmax`` over these is the greedy
        policy (sts2_rl.evaluation.torch_policy)."""
        return self.actor(_as_flat(obs)).masked_fill(~mask, _MASK_FILL)

    def _dist(self, obs: torch.Tensor, mask: torch.Tensor) -> Categorical:
        return Categorical(logits=self.action_logits(obs, mask))

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
        # Each segment's [start, stop) span in the ENCODED vector — i.e. the
        # columns of the following trunk's first Linear that this segment
        # feeds. Encoded, not raw: vocabulary segments contract to an
        # embedding, so the two layouts differ (run.map.grid is 6% of the flat
        # obs but 50% of the columns, because it stays raw).
        self.out_spans: dict[str, tuple[int, int]] = {}
        self.out_dim = 0
        offset = 0
        for name, width in segments:
            out_start = self.out_dim
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
            self.out_spans[name] = (out_start, self.out_dim)
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

    def get_value(self, obs: torch.Tensor | TensorObs) -> torch.Tensor:
        return self.critic(self.critic_encoder(_as_flat(obs))).squeeze(-1)

    def action_logits(self, obs: torch.Tensor | TensorObs, mask: torch.Tensor) -> torch.Tensor:
        """Masked policy logits — same contract as
        ``MaskedActorCritic.action_logits``."""
        return self.actor(self.actor_encoder(_as_flat(obs))).masked_fill(~mask, _MASK_FILL)

    def _dist(self, obs: torch.Tensor | TensorObs, mask: torch.Tensor) -> Categorical:
        return Categorical(logits=self.action_logits(obs, mask))

    def get_action_and_value(
        self,
        obs: torch.Tensor | TensorObs,
        mask: torch.Tensor,
        action: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns ``(action, log_prob, entropy, value)`` — same contract as
        ``MaskedActorCritic.get_action_and_value``."""
        dist = self._dist(obs, mask)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.get_value(obs)


# ── entity-SET architecture (--arch entset) — OBS_SCHEMA.md v4 ──────────────
#
# The schema-v4 replacement for EntityActorCritic above: it consumes the
# {"f", "i"} pair DIRECTLY (as a TensorObs) instead of a flat obs slice, one
# row per entity instance rather than one dict slot per id.

N_AFFLICTIONS = CAPACITIES["afflictions"]
N_ENCHANTMENTS = CAPACITIES["enchantments"]

# Embedding width per vocabulary kind for the entset encoder. A separate
# table from EntityActorCritic's EMBED_DIMS above (frozen with that arch) —
# entset's own row-projection scheme has different dimensionality trade-offs
# and two vocabularies (afflictions/enchantments) EMBED_DIMS never had.
ENTSET_EMBED_DIMS: dict[str, int] = {
    "cards": 32,
    "relics": 16,
    "powers": 16,
    "monsters": 16,
    "potions": 8,
    "events": 8,
    "purposes": 4,
    "afflictions": 4,
    "enchantments": 8,
}

_ENTSET_VOCAB_ROWS: dict[str, int] = {
    "cards": N_CARDS, "relics": N_RELICS, "powers": N_POWERS,
    "monsters": N_MONSTERS, "potions": N_POTIONS, "events": N_EVENTS,
    "purposes": N_PURPOSES, "afflictions": N_AFFLICTIONS,
    "enchantments": N_ENCHANTMENTS,
}

# Explicit segment -> per-int-field vocabulary map, replacing _segment_plan's
# name-suffix-plus-width-match inference (which stays as EntityActorCritic's
# own, frozen, v3-era mechanism). Keyed by the LOGICAL block name: an
# ``.ids`` segment name with any leading run-env "combat." prefix and the
# trailing ".ids" both stripped, so one entry covers a segment whether it's
# read from ``full_env.combat_obs_layout()`` directly (--env combat) or
# folded into ``run_env.run_obs_layout()`` under the "combat." prefix
# (--env run/column).
#
# ``None`` marks a literal field that indexes no vocabulary (OBS_SCHEMA.md
# §5.1's ``cards.ids``/``run.deck.ids`` etc. leading ``pile_id``) — declared
# explicitly per field, never omitted, so an undeclared field is a loud
# KeyError/ValueError (via entset_segment_plan below) rather than a segment
# silently falling through to "just floats" and training against garbage.
_ENTSET_SEGMENT_VOCABS: dict[str, tuple[str | None, ...]] = {
    "player.powers": ("powers",),
    "player.relics": ("relics",),
    "hand": ("cards", "afflictions", "enchantments"),
    "enemies": ("monsters",),
    "potions": ("potions",),
    "cards": (None, "cards", "afflictions", "enchantments"),
    "run.potions": ("potions",),
    "run.deck": (None, "cards", "afflictions", "enchantments"),
    "run.relics": ("relics",),
    "run.boss": ("monsters",),
    "event": ("events",),
    "shop.cards": ("cards",),
    "shop.relics": ("relics",),
    "shop.potions": ("potions",),
    "reward.cards": (None, "cards", "afflictions", "enchantments"),
    "reward.potion": ("potions",),
    "reward.relic": ("relics",),
    "select.purpose": ("purposes",),
    "select.candidates": (None, "cards", "afflictions", "enchantments"),
}
for _e in range(MAX_ENEMIES):
    _ENTSET_SEGMENT_VOCABS[f"enemy{_e}.powers"] = ("powers",)
del _e


def _entset_logical_name(ids_segment_name: str) -> str:
    """``"combat.hand.ids"`` / ``"hand.ids"`` -> ``"hand"``."""
    # A bare `assert` is a no-op under `python -O` (assertions are
    # stripped), silently disarming this check exactly where it matters —
    # every `i_segment` this project actually emits is `.ids`-suffixed
    # today, but a future segment name that broke that convention would
    # otherwise pass through and corrupt `entset_segment_plan`'s vocab
    # lookup silently. Raise explicitly instead (same fix as
    # run_env.py's MAX_OBS_ID check).
    if not ids_segment_name.endswith(".ids"):
        raise ValueError(
            f"_entset_logical_name: {ids_segment_name!r} does not end in "
            f"'.ids' -- every i_segment name is expected to (OBS_SCHEMA.md "
            f"Sec.2's naming convention).")
    name = ids_segment_name[: -len(".ids")]
    if name.startswith("combat."):
        name = name[len("combat."):]
    return name


def _slices(segments: list[tuple[str, int]]) -> dict[str, slice]:
    out: dict[str, slice] = {}
    offset = 0
    for name, width in segments:
        out[name] = slice(offset, offset + width)
        offset += width
    return out


def entset_segment_plan(
    f_segments: list[tuple[str, int]], i_segments: list[tuple[str, int]],
) -> tuple[list[tuple[str, int, int, tuple[str | None, ...]]], list[tuple[str, int]]]:
    """Pair every ``.ids`` segment with its declared vocab tuple and its
    (maybe absent) ``.f`` sibling.

    Returns ``(row_blocks, raw_f_segments)``:

    * ``row_blocks`` — ``(name, cap, n_float, vocabs)`` per ``.ids`` segment,
      in layout order. ``cap`` and the paired ``.f`` block's per-row float
      count are both DERIVED from declared field counts and observed
      widths, never hardcoded — a mismatch (a segment's width not a
      multiple of its declared field count, or the paired ``.f`` block's
      width not a multiple of the derived ``cap``) raises rather than
      silently truncating. ``n_float`` is ``0`` for the two blocks with no
      row-shaped float sibling at all (``event``, ``select.purpose`` — both
      single scalars, see OBS_SCHEMA.md §5A).
    * ``raw_f_segments`` — every ``.f`` segment NOT consumed by a row block
      above (plain numeric segments: vitals, the map grid, every
      ``.overflow`` flag, ...), in layout order.

    This also serves as a completeness check: called against both envs'
    REAL layouts (as the model-construction path does), an undeclared
    ``.ids`` segment or a width that doesn't divide evenly raises
    immediately — see ``test_tensor_obs.py``'s sibling,
    ``test/test_models.py``-equivalent coverage in this lane's own tests.
    """
    f_widths = dict(f_segments)
    row_blocks: list[tuple[str, int, int, tuple[str | None, ...]]] = []
    consumed_f: set[str] = set()
    for name, width in i_segments:
        logical = _entset_logical_name(name)
        vocabs = _ENTSET_SEGMENT_VOCABS.get(logical)
        if vocabs is None:
            raise ValueError(
                f"entset: obs segment {name!r} (logical {logical!r}) has no "
                f"declared vocab mapping in models._ENTSET_SEGMENT_VOCABS -- "
                f"add one (use None per field for a literal that indexes no "
                f"vocabulary) instead of letting it fall through silently.")
        n_int = len(vocabs)
        if n_int == 0 or width % n_int != 0:
            raise ValueError(
                f"entset: obs segment {name!r} has width {width}, not an "
                f"even multiple of its declared field count {n_int}.")
        cap = width // n_int
        f_name = f"{name[:-len('.ids')]}.f"
        if f_name in f_widths:
            f_width = f_widths[f_name]
            if f_width % cap != 0:
                raise ValueError(
                    f"entset: obs segment {f_name!r} has width {f_width}, "
                    f"not an even multiple of the {cap} rows {name!r} "
                    f"declares.")
            n_float = f_width // cap
            consumed_f.add(f_name)
        else:
            n_float = 0
        row_blocks.append((name, cap, n_float, vocabs))
    raw_f_segments = [(n, w) for n, w in f_segments if n not in consumed_f]
    return row_blocks, raw_f_segments


class _EntsetEncoder(neural_network.Module):
    """Masked sum-pool of per-row embeddings, plus per-field projections.

    One ``nn.Embedding(capacity + 1, dim, padding_idx=0)`` per vocabulary
    kind (OBS_SCHEMA.md §2.1's PAD convention: id 0 is reserved, so an
    absent row's embedding is exactly zero and needs no separate mask
    multiply on the embedding side). Per ``.ids`` block: reshape to
    ``(rows, n_int)``, embed each int field (a literal field with no vocab
    is passed through as a plain float instead), concatenate with that
    row's floats, project through one ``Linear`` + ``Tanh``, and masked
    sum-pool over rows — the mask is the row's PRIMARY field (the first
    vocab-mapped int field in declaration order) being non-PAD, which is
    the field that determines whether the row exists at all (OBS_SCHEMA.md
    §2.1); a literal-only leading field such as ``cards.ids``' ``pile_id``
    is never PAD-reliable on its own (``run.deck``'s rows all carry
    ``pile_id == PAD`` outside combat, present row or not) so it is
    deliberately skipped when picking the primary field.
    """

    def __init__(
        self,
        f_segments: list[tuple[str, int]],
        i_segments: list[tuple[str, int]],
        embed_dims: dict[str, int] | None = None,
        block_dim: int = 32,
    ) -> None:
        super().__init__()
        dims = dict(ENTSET_EMBED_DIMS, **(embed_dims or {}))
        row_blocks, raw_f_segments = entset_segment_plan(f_segments, i_segments)

        self.tables = neural_network.ModuleDict()
        for kind in sorted(_ENTSET_VOCAB_ROWS):
            table = neural_network.Embedding(
                _ENTSET_VOCAB_ROWS[kind] + 1, dims[kind], padding_idx=0)
            with torch.no_grad():
                neural_network.init.orthogonal_(table.weight[1:], np.sqrt(2))
                table.weight[0].zero_()
            self.tables[kind] = table

        self.block_dim = block_dim
        i_slices = _slices(i_segments)
        f_slices = _slices(f_segments)
        self._blocks: neural_network.ModuleList = neural_network.ModuleList()
        self._block_meta: list[dict] = []
        self.out_spans: dict[str, tuple[int, int]] = {}
        seen_logical: set[str] = set()
        out_dim = 0
        for name, cap, n_float, vocabs in row_blocks:
            n_int = len(vocabs)
            row_in = sum(1 if v is None else dims[v] for v in vocabs) + n_float
            proj = _layer_init(neural_network.Linear(row_in, block_dim))
            self._blocks.append(proj)
            primary = next(idx for idx, v in enumerate(vocabs) if v is not None)
            f_name = f"{name[:-len('.ids')]}.f"
            logical = _entset_logical_name(name)
            if logical in seen_logical:
                raise ValueError(
                    f"entset: two row blocks strip to the same logical name "
                    f"{logical!r} in this layout -- {name!r} collides with "
                    f"an earlier segment; `encode`'s `rows` dict cannot key "
                    f"both.")
            seen_logical.add(logical)
            self._block_meta.append(dict(
                i_slice=i_slices[name],
                f_slice=f_slices.get(f_name),
                cap=cap, n_int=n_int, n_float=n_float,
                vocabs=vocabs, primary=primary, logical=logical,
            ))
            out_start = out_dim
            out_dim += block_dim
            self.out_spans[name[:-len(".ids")]] = (out_start, out_dim)

        self._raw_slices: list[tuple[str, slice]] = []
        for name, width in raw_f_segments:
            out_start = out_dim
            out_dim += width
            self.out_spans[name] = (out_start, out_dim)
            self._raw_slices.append((name, f_slices[name]))
        self.out_dim = out_dim
        # Named lookup into EVERY named ``.f`` segment's slice of ``obs.f``
        # -- both the ones no row block consumes (``choice_float_overlays``'
        # need, e.g. one ``map{k}`` slot or ``shop.removal``) AND the ones a
        # row block DOES consume for its own pooled/embedded row features
        # (the play head's pair-feature tensor needs ``enemies.f``'s raw
        # incoming-attack preview columns even though ``enemies.f`` is also
        # the float sibling of the ``enemies.ids`` row block; one dict
        # covers both callers rather than duplicating span arithmetic).
        # Built from the full ``f_slices`` map, not just ``self._raw_slices``.
        self.raw_f_index: dict[str, slice] = dict(f_slices)

    def raw(self, obs: TensorObs, name: str) -> torch.Tensor:
        """Slice one named ``.f`` segment straight out of ``obs.f`` --
        ``choice_float_overlays`` float-segment content, and the play
        head's pair-feature segments, some of which (``enemies.f``) are
        ALSO a row block's float sibling elsewhere in this encoder."""
        return obs.f[..., self.raw_f_index[name]]

    def play_pair_features(
        self, obs: TensorObs, dm_name: str, enemy_f_name: str, S: int, T: int,
    ) -> torch.Tensor:
        """The play ``PairPointerHead``'s per-(hand, enemy) pair-feature
        tensor, ``(..., S, T, 7)``.

        Feature 0 is the ``dm_name`` segment (``damage_matrix`` / ``combat.
        damage_matrix``) reshaped to ``(S, T, 1)`` -- it is already written
        row-major ``h*MAX_ENEMIES + e`` (``full_env._write_damage_matrix``),
        one clipped ``per_hit/ABS_SCALE`` scalar per pair, so the reshape
        alone recovers the (hand, enemy) grid; no reordering needed.

        Features 1-6 are ``enemy_f_name``'s (``enemies.f`` / ``combat.
        enemies.f``) per-enemy incoming-attack preview -- fields 18:24 of
        each enemy's 25-float row (``full_env._enemy_floats``: ``pb = 18``
        starts ``per_hit, hits, total_fine, total_coarse, post_block_fine,
        post_block_coarse``) -- broadcast across the hand axis, since the
        preview is a property of the ENEMY, not the (card, enemy) pair.
        """
        batch_shape = obs.f.shape[:-1]
        dm = self.raw(obs, dm_name).reshape(*batch_shape, S, T, 1)
        ef_raw = self.raw(obs, enemy_f_name)
        n_float = ef_raw.shape[-1] // T
        ef = ef_raw.reshape(*batch_shape, T, n_float)[..., _PLAY_PAIR_PREVIEW_SLICE]
        ef = ef.unsqueeze(-3).expand(*([-1] * len(batch_shape)), S, -1, -1)
        return torch.cat([dm, ef], dim=-1)

    def encode(self, obs: TensorObs) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        """Like :meth:`forward`, but also returns the per-row-block,
        mask-multiplied row tensors ``forward`` discards after pooling --
        the tied action head needs these same per-row features. ``rows`` is
        keyed by each block's LOGICAL name (the
        ``_entset_logical_name``-stripped form the ``combat.`` run-env prefix
        collapses onto the combat env's own names) -- collisions within one
        layout are a construction-time error (see ``__init__``), not a
        silent overwrite here.

        A PAD row is an exact zero VECTOR in ``rows`` (``projected * mask``
        with a zero mask row), not ``tanh(bias)`` -- the same masked value
        ``forward``'s pooled sum already summed over, just not yet summed.
        """
        f, i = obs.f, obs.i
        parts: list[torch.Tensor] = []
        rows: dict[str, torch.Tensor] = {}
        for proj, meta in zip(self._blocks, self._block_meta):
            cap, n_int = meta["cap"], meta["n_int"]
            ids = i[..., meta["i_slice"]].reshape(*i.shape[:-1], cap, n_int)
            pieces: list[torch.Tensor] = []
            for j, vocab in enumerate(meta["vocabs"]):
                col = ids[..., j]
                if vocab is None:
                    pieces.append(col.unsqueeze(-1).to(f.dtype))
                else:
                    pieces.append(self.tables[vocab](col))
            if meta["n_float"]:
                floats = f[..., meta["f_slice"]].reshape(*f.shape[:-1], cap, meta["n_float"])
                pieces.append(floats)
            row = torch.cat(pieces, dim=-1)
            projected = torch.tanh(proj(row))
            # OBS_SCHEMA.md Sec.2.1: a padded row is `id == 0` AND all-zero
            # floats, so present = NOT that conjunction = id != 0 OR any
            # float in the row nonzero. Checking the id column alone (the
            # previous form of this line) silently drops any row that
            # carries a PAD id with live floats -- e.g. `hand` under
            # `--card-obs features` (PAD card_id, 29 real feature floats) and
            # `run.potions`' empty-but-existing belt slots (PAD potion id,
            # live `slot_exists` float). Both envs are correct; a mask that
            # only reads half the schema's own padding rule was not.
            present = ids[..., meta["primary"]] != 0
            if meta["n_float"]:
                present = present | (floats != 0).any(dim=-1)
            mask = present.to(f.dtype).unsqueeze(-1)
            masked = projected * mask
            parts.append(masked.sum(dim=-2))
            rows[meta["logical"]] = masked
        for name, sl in self._raw_slices:
            parts.append(f[..., sl])
        return torch.cat(parts, dim=-1), rows

    def forward(self, obs: TensorObs) -> torch.Tensor:
        return self.encode(obs)[0]


#: The play head's per-pair preview slice into each enemy's 25-float
#: `enemies.f` row -- `full_env._enemy_floats`'s `pb = 18` starts
#: `per_hit, hits, total_fine, total_coarse, post_block_fine,
#: post_block_coarse` (6 fields).
_PLAY_PAIR_PREVIEW_SLICE = slice(18, 24)
#: 1 (damage_matrix) + 6 (the preview slice above) = the play head's
#: `pair_dim` whenever `ActionLayout.play_pair_feature_segments` is set.
_PLAY_PAIR_DIM = 1 + (_PLAY_PAIR_PREVIEW_SLICE.stop - _PLAY_PAIR_PREVIEW_SLICE.start)


#: Version of the ``entset`` action head's PARAMETER STRUCTURE **and its
#: layout SEMANTICS** -- not the obs schema (that is
#: ``checkpoints.obs_schema_version``), and not the arch name (which stays
#: ``"entset"`` across both). Bump this on any change that alters how the
#: entset head's weights are laid out, so a checkpoint trained under the old
#: structure gets ``checkpoints.check_checkpoint``'s honest "predates this
#: change, use --fresh" refusal instead of a raw ``load_state_dict`` key
#: error.
#:
#: **Bump it also for semantic-only ``ActionLayout`` changes that alter no
#: weight shape** (final whole-branch review, 2026-08-02): the layout is
#: rebuilt from CURRENT code at load time and is not stamped into the
#: checkpoint, so e.g. moving an overlay's CHOICE-slot offset, or repointing
#: a pointer block at a different row block of the same ``block_dim``,
#: reloads an old checkpoint silently with a head now scoring the WRONG
#: action slot -- zero shape mismatch, zero state-dict error, wrong policy.
#: The narrow "weights laid out" rule above would let that through; this
#: broader rule is the guard until a layout fingerprint is stamped instead.
#:
#: * 1 -- one opaque positional ``nn.Linear(hidden[-1], n_actions)`` action
#:   head.
#: * 2 -- "tied action head": the positional head is replaced by
#:   ``ActionLayout`` + a handful of ``PairPointerHead``s tied to the
#:   encoder's own row embeddings (see ``EntitySetActorCritic`` below).
#: * 3 -- "pointer scoring for content-carrying run decisions": the run
#:   env's SELECT and belt-POTION ranges move from a positional ``Linear``
#:   to a ``PointerHead`` each (``ActionLayout.pointer_blocks``), and the
#:   CHOICE range gains additive ``PointerHead``/``FloatPointerHead``
#:   overlays scored from the same-decision content rows/float segments
#:   (``ActionLayout.choice_row_overlays`` / ``choice_float_overlays``) --
#:   new parameters with no state-dict counterpart in a version-2 checkpoint.
#: * 4 -- "pair features in the tied combat head": the play
#:   ``PairPointerHead``'s first ``Linear`` widens from
#:   ``src_dim + tgt_dim + 32`` to ``src_dim + tgt_dim + 32 + 7`` (the
#:   ``damage_matrix`` scalar plus the 6-float incoming-attack preview, per
#:   (hand, enemy) pair -- ``ActionLayout.play_pair_feature_segments``,
#:   ``_EntsetEncoder.play_pair_features``). The potion pair head is
#:   unchanged (potions have no damage matrix, so ``pair_dim`` stays 0
#:   there) -- but the play head's weight SHAPE changed, so a version-3
#:   checkpoint's ``play_head.mlp.0.weight`` no longer matches.
#:
#: * 5 -- v22 discard block: run layout appends a third pointer block
#:   (DISCARD_BASE, over the same ``run.potions`` rows) -- pointer_heads
#:   gains index 2 and N_ACTIONS widens by MAX_POTION_SLOTS. Combat-scale
#:   layouts are UNCHANGED (a combat checkpoint migrates by restamp alone).
#:
#: ``checkpoints.check_checkpoint`` treats a checkpoint with no ``head_version``
#: key as version 1 (every checkpoint saved before this constant existed was,
#: by construction, a version-1 head).
ENTSET_HEAD_VERSION = 5


@dataclass(frozen=True)
class ActionLayout:
    """Declarative map from logit index ranges to scoring mechanisms (T7
    brief) -- what used to be one opaque positional ``Linear(hidden[-1],
    n_actions)`` is now assembled range by range, each range naming the row
    blocks (keyed exactly as ``_EntsetEncoder.encode``'s ``rows`` dict keys
    them) it pairs, or a plain width for a still-positional range.

    Ranges tile ``[0, n_actions)`` with NO gap and NO overlap, in this fixed
    order: ``end_turn_index`` (width 1, always index 0 when present) ->
    ``play`` (width ``S*T``) -> ``potion_pairs`` (width ``S_used*T``) -> then
    every ``positional`` and ``pointer_blocks`` range TOGETHER, ordered by
    ascending ``base`` (each range's ``base`` must equal where the previous
    one ended). ``EntitySetActorCritic`` checks this tiling at construction
    (``_validate_action_layout``) rather than waiting for a shape mismatch
    inside ``forward``.

    ``pointer_blocks`` is a whole-range REPLACEMENT for a positional
    ``Linear`` (SELECT-by-candidate, the belt-POTION block). Two overlay
    groups add ADDITIVE content-derived terms onto one ``positional`` range
    (CHOICE, named by ``choice_base``) rather than replacing it: CHOICE's own
    ``Linear`` still runs (REST/EVENT/SELECT_OPTION/REWARD_POTION have no
    content rows, so the positional score is the only signal for those
    slots), and content rows for the mechanisms that DO carry them
    (REWARD_CARD, SHOP, MAP) add an extra per-slot term on top, computed
    straight from the same encoder rows the observation already produced --
    no obs schema change.
    """

    n_actions: int
    end_turn_index: int | None                       # 0, or None if absent
    play: tuple[str, str, int, int] | None            # (src_block, tgt_block, S, T), base = end_turn_index + 1
    potion_pairs: tuple[str, str, int, int] | None    # (src_block, tgt_block, S_used, T); src rows sliced [..., :S_used, :]
    positional: tuple[tuple[int, int], ...] = ()      # (base, width) ranges scored by plain Linear(ctx)
    pointer_blocks: tuple[tuple[int, int, str], ...] = ()
    # (base, width, row_block): the ENTIRE action range [base, base+width) is
    # scored by a PointerHead over rows[row_block][..., :width, :],
    # REPLACING the positional Linear for that range.
    choice_base: int | None = None
    # The `base` of the one `positional` range the overlays below add onto
    # (always CHOICE_BASE in this codebase's only user, `run_action_layout`)
    # -- `None` iff neither overlay group is used.
    choice_row_overlays: tuple[tuple[int, int, str, int], ...] = ()
    # (choice_slot_base_offset, n_slots, row_block, row_offset): ADDITIVE
    # overlay onto the positional CHOICE logits -- slot (choice_base +
    # choice_slot_base_offset + k) += pointer_score(rows[row_block][row_offset + k])
    # for k in range(n_slots).
    choice_float_overlays: tuple[tuple[int, int, str], ...] = ()
    # (choice_slot_base_offset, n_slots, segment_prefix): same, but the
    # content is a RAW float segment, not an entity row block: for k in
    # range(n_slots) the source is float segment f"{segment_prefix}{k}"
    # (e.g. "map0".."map6"), or the bare `segment_prefix` itself when
    # n_slots == 1 and no indexed sibling exists (e.g. "shop.removal", which
    # has no "shop.removal0") -- projected by a SHARED Linear+tanh to 32
    # dims then scored by a FloatPointerHead, presence-gated on the raw
    # floats being not-all-zero.
    play_pair_feature_segments: tuple[str, ...] = ()
    # (damage_matrix_segment_name, enemies_f_segment_name). Either empty (no
    # pair features -- `potion_pairs` always has none) or exactly these two
    # RAW `.f` segment names, in this order:
    #
    # * feature 0 -- `damage_matrix` (combat) / `combat.damage_matrix`
    #   (run), reshaped to (S, T, 1): one clipped per-hit scalar per (hand,
    #   enemy) pair, already row-major h*MAX_ENEMIES+e
    #   (`full_env._write_damage_matrix`).
    # * features 1-6 -- `enemies.f` / `combat.enemies.f`, sliced to fields
    #   18:24 per enemy row (`full_env._enemy_floats`'s `pb = 18`:
    #   per_hit/hits/total_fine/total_coarse/post_block_fine/
    #   post_block_coarse) and broadcast across the hand axis.
    #
    # Carries segment NAMES (not hardcoded strings in the model body) so
    # the run env's `combat.`-prefixed siblings resolve through the same
    # `_EntsetEncoder.play_pair_features` call as the combat env's bare
    # names (`combat_action_layout` / `run_action_layout`). Only meaningful
    # when `play` is also set; `_validate_action_layout` rejects the
    # reverse. `EntitySetActorCritic.__init__` checks both names exist as
    # raw `.f` segments and that their widths are consistent with `play`'s
    # (S, T) before wiring `play_head`'s `pair_dim`.


def _validate_action_layout(layout: ActionLayout) -> None:
    """Structural tiling check: end_turn(1) + play(S*T) +
    potion_pairs(S_used*T) + every ``positional``-or-``pointer_blocks``
    range's width (the two groups merged and sorted by ``base``, since a
    range can be either mechanism) sums to exactly ``n_actions``, with no
    gap, no overlap. Raises ``ValueError`` (a loud construction-time error)
    rather than silently building a model whose logits don't cover -- or
    overlap -- the action space.

    If either overlay group is declared, ``choice_base`` must name one of
    ``positional``'s own ranges, and every overlay entry
    (``choice_row_overlays``/``choice_float_overlays``) must lie entirely
    inside that range's ``[0, width)`` -- an overlay that pokes outside the
    CHOICE range it's meant to augment is a construction-time error, not a
    silent out-of-bounds add at forward time.

    ``play_pair_feature_segments``, if non-empty, must have exactly 2
    entries (the ``damage_matrix``/``enemies.f`` pair, in that order) and
    ``play`` must be set -- pair features with no play range to attach them
    to is a construction-time error, not a silently-ignored field. (Segment
    existence and width consistency need the encoder's real segment plan,
    so those checks live in ``EntitySetActorCritic.__init__``, not here.)
    """
    if layout.play_pair_feature_segments:
        if layout.play is None:
            raise ValueError(
                "ActionLayout declares play_pair_feature_segments but "
                "play is None -- pair features have no play range to "
                "attach to.")
        if len(layout.play_pair_feature_segments) != 2:
            raise ValueError(
                f"ActionLayout.play_pair_feature_segments must have exactly "
                f"2 entries (damage_matrix_name, enemies_f_name), got "
                f"{layout.play_pair_feature_segments!r}.")

    pos = 0
    if layout.end_turn_index is not None:
        if layout.end_turn_index != 0:
            raise ValueError(
                f"ActionLayout.end_turn_index must be 0 when present (saw "
                f"{layout.end_turn_index!r}) -- every action layout in this "
                f"codebase reserves logit 0 for end-turn.")
        pos = 1
    if layout.play is not None:
        _src, _tgt, S, T = layout.play
        pos += S * T
    if layout.potion_pairs is not None:
        _src, _tgt, S, T = layout.potion_pairs
        pos += S * T

    tail = [(base, width) for base, width in layout.positional]
    tail += [(base, width) for base, width, _row_block in layout.pointer_blocks]
    tail.sort(key=lambda bw: bw[0])
    for base, width in tail:
        if base != pos:
            raise ValueError(
                f"ActionLayout range (base={base}, width={width}) does not "
                f"start exactly where the previous range ended ({pos}) -- "
                f"layout has a gap or overlap.")
        pos += width
    if pos != layout.n_actions:
        raise ValueError(
            f"ActionLayout ranges sum to {pos} logits but n_actions is "
            f"{layout.n_actions}.")

    if layout.choice_row_overlays or layout.choice_float_overlays:
        if layout.choice_base is None:
            raise ValueError(
                "ActionLayout declares choice overlays but choice_base is "
                "None -- overlays need to name the positional CHOICE range "
                "they add onto.")
        choice_width = next(
            (w for base, w in layout.positional if base == layout.choice_base),
            None)
        if choice_width is None:
            raise ValueError(
                f"ActionLayout.choice_base ({layout.choice_base}) does not "
                f"match any positional range's base.")
        for offset, n_slots, _row_block, _row_offset in layout.choice_row_overlays:
            if offset < 0 or n_slots < 0 or offset + n_slots > choice_width:
                raise ValueError(
                    f"choice_row_overlays entry (offset={offset}, "
                    f"n_slots={n_slots}) escapes the CHOICE range "
                    f"[0, {choice_width}).")
        for offset, n_slots, _prefix in layout.choice_float_overlays:
            if offset < 0 or n_slots < 0 or offset + n_slots > choice_width:
                raise ValueError(
                    f"choice_float_overlays entry (offset={offset}, "
                    f"n_slots={n_slots}) escapes the CHOICE range "
                    f"[0, {choice_width}).")


def combat_action_layout(max_potions: int) -> ActionLayout:
    """The combat env's own action layout: end-turn scalar, a play pointer
    pairing every ``hand`` row against every ``enemies`` row, and a potion
    pointer pairing the first ``max_potions`` ``potions`` rows against every
    ``enemies`` row -- exactly ``full_env.decode_combat_action``'s
    ``h*MAX_ENEMIES + e`` / ``p*MAX_ENEMIES + e`` ordering. No positional
    ranges: combat has nothing else to score.

    The play pointer also gets ``play_pair_feature_segments`` --
    ``damage_matrix`` and ``enemies.f`` are both already real ``.f``
    segments in this env's own layout (no obs schema change), so the play
    head can see the one number that most decides a play: the damage THIS
    card would do to THIS enemy, plus that enemy's incoming-attack preview.
    ``potion_pairs`` gets none -- potions have no damage matrix."""
    return ActionLayout(
        n_actions=combat_action_count(max_potions),
        end_turn_index=0,
        play=("hand", "enemies", MAX_HAND, MAX_ENEMIES),
        potion_pairs=("potions", "enemies", max_potions, MAX_ENEMIES),
        positional=(),
        play_pair_feature_segments=("damage_matrix", "enemies.f"),
    )


def run_action_layout() -> ActionLayout:
    """The run/curriculum envs' action layout: the SAME combat pointer heads
    as ``combat_action_layout`` (the embedded ``combat.*`` block, whose
    row-block names ``_entset_logical_name`` already strips back to
    ``"hand"``/``"enemies"``/``"potions"`` -- see ``models._entset_logical_name``),
    sized to ``run_env.MAX_POTION_SLOTS`` (the belt's true worst case),
    followed by the CHOICE/SELECT/belt-POTION ranges:

    * CHOICE stays positional (``positional``) -- REST/EVENT/SELECT_OPTION/
      REWARD_POTION have no per-option content rows in the observation, so a
      plain ``Linear(ctx)`` is the only signal those slots can get -- but
      gains ADDITIVE overlays (``choice_row_overlays``/``choice_float_overlays``)
      from the mechanisms that DO carry content: REWARD_CARD
      (``reward.cards``), SHOP (``shop.cards``/``shop.relics``/``shop.potions``
      rows, plus the ``shop.removal`` float triple for the removal slot --
      its only content is cost, and cost IS content), and MAP (the
      ``map0``..``map6`` float blocks). Offsets are CHOICE-relative slot
      indices: reward cards 0-2, shop cards 0-6, shop relics 7-9, shop
      potions 10-12, shop removal 13, map options 0-6 -- all sharing offset
      0 across kinds is safe because exactly one kind's rows/floats are ever
      non-PAD/non-zero for a given decision (presence gating makes every
      other kind's contribution exactly 0).
    * SELECT and belt-POTION are REPLACED by ``pointer_blocks`` entries --
      ``select.candidates``/``run.potions`` rows are already in the SAME
      order the action space indexes (CHOICE_BASE+i / SELECT_BASE+i /
      POTION_BASE+i answer ``own_actions()``'s entry i, unreordered), so a
      PointerHead over those rows scores each option from its own content
      instead of an opaque per-slot bias.

    ``run_env`` is imported lazily (function-local), mirroring
    ``checkpoints.py``'s own "env/run-scale imports are lazy" convention --
    importing it eagerly would drag greenlet into every ``import
    sts2_rl.models``, even for combat-only callers. There is no genuine
    import CYCLE here (``run_env`` imports neither ``models`` nor
    ``checkpoints``), so this is purely an import-cost choice, not a
    correctness requirement.
    """
    from .run_env import (
        CHOICE_BASE,
        CHOICE_SLOTS,
        DISCARD_BASE,
        MAX_POTION_SLOTS,
        MAX_SELECT_CANDIDATES,
        N_ACTIONS,
        POTION_BASE,
        REWARD_CARD_SLOTS,
        SELECT_BASE,
    )

    return ActionLayout(
        n_actions=N_ACTIONS,
        end_turn_index=0,
        play=("hand", "enemies", MAX_HAND, MAX_ENEMIES),
        potion_pairs=("potions", "enemies", MAX_POTION_SLOTS, MAX_ENEMIES),
        positional=(
            (CHOICE_BASE, CHOICE_SLOTS),
        ),
        # Same play_pair_feature_segments mechanism as combat_action_layout,
        # but naming the run env's OWN `combat.`-prefixed segments (the raw
        # `.f` index is keyed by literal segment name, unlike the row blocks
        # above -- those key by logical name).
        play_pair_feature_segments=("combat.damage_matrix", "combat.enemies.f"),
        pointer_blocks=(
            (SELECT_BASE, MAX_SELECT_CANDIDATES, "select.candidates"),
            (POTION_BASE, MAX_POTION_SLOTS, "run.potions"),
            # v22: discard scored from the SAME belt rows by its own head.
            # MUST stay LAST -- pointer_heads.2 is the only key set the
            # head-v5 migration fresh-initializes (tools/migrate_headv5.py).
            (DISCARD_BASE, MAX_POTION_SLOTS, "run.potions"),
        ),
        choice_base=CHOICE_BASE,
        choice_row_overlays=(
            (0, REWARD_CARD_SLOTS, "reward.cards", 0),
            (0, 7, "shop.cards", 0),
            (7, 3, "shop.relics", 0),
            (10, 3, "shop.potions", 0),
        ),
        choice_float_overlays=(
            (0, 7, "map"),
            (13, 1, "shop.removal"),
        ),
    )


class EntitySetActorCritic(neural_network.Module):
    """``--arch entset`` — the schema-v4 architecture (module docstring;
    OBS_SCHEMA.md §2.2). Same masked-categorical policy contract
    as the other two archs (separate actor/critic trunks AND encoders); the
    one difference is that ``obs`` here is a
    :class:`~sts2_rl.tensor_obs.TensorObs`, not a flat tensor — the encoder
    needs both halves together to embed by id and attach that id's floats.

    Tied action head: the actor side is not one opaque positional
    ``Linear(hidden[-1], n_actions)``. The actor trunk is a pure FEATURE
    trunk (``_trunk``, same widths/init, no final layer) whose output
    ``ctx`` feeds a handful of heads assembled per ``action_layout``: an
    end-turn scalar head, a ``PairPointerHead`` over (play) row pairs, a
    second (separately-weighted) ``PairPointerHead`` over (potion) row
    pairs, and one plain ``Linear(ctx)`` per still-positional range. The
    critic side (separate encoder, pooled ``forward``, value head) is
    UNTOUCHED. ``action_layout`` is a required argument (no positional
    fallback) -- a wrong layout must fail loudly at construction, not
    silently degrade.
    """

    arch = "entset"

    def __init__(
        self,
        f_segments: list[tuple[str, int]],
        i_segments: list[tuple[str, int]],
        n_actions: int,
        action_layout: ActionLayout,
        hidden: tuple[int, ...] = (256, 256),
        embed_dims: dict[str, int] | None = None,
        shared_encoder: bool = False,
    ) -> None:
        super().__init__()
        self.f_segments = list(f_segments)
        self.i_segments = list(i_segments)
        f_dim = sum(w for _, w in f_segments)
        i_dim = sum(w for _, w in i_segments)
        self.obs_dim = (f_dim, i_dim)
        self.n_actions = n_actions
        self.hidden = tuple(hidden)
        self.shared_encoder = shared_encoder

        if action_layout.n_actions != n_actions:
            raise ValueError(
                f"action_layout.n_actions ({action_layout.n_actions}) != "
                f"n_actions ({n_actions}) passed to EntitySetActorCritic.")
        _validate_action_layout(action_layout)
        self.action_layout = action_layout

        self.actor_encoder = _EntsetEncoder(f_segments, i_segments, embed_dims)
        if shared_encoder:
            # One shared `_EntsetEncoder` instance serves BOTH the actor and
            # the critic -- the whole per-row embed/project/pool stack, not
            # tables-only sharing. `object.__setattr__` bypasses nn.Module's
            # own `__setattr__`, which would otherwise register this SAME
            # encoder object a second time under the name "critic_encoder"
            # -- harmless for forward (it's still the same tensors either
            # way) but would duplicate every one of its parameters under two
            # keys in state_dict()/named_parameters(). The two separate
            # trunks (`self.actor`/`self.critic`) and heads are UNCHANGED by
            # this flag -- only the encoder is shared.
            object.__setattr__(self, "critic_encoder", self.actor_encoder)
        else:
            self.critic_encoder = _EntsetEncoder(f_segments, i_segments, embed_dims)

        # Construction-time check that every row block the layout names
        # actually exists in this encoder's segment plan -- and, where the
        # layout also declares a row count, that it agrees with the block's
        # real cap -- rather than waiting for a KeyError/shape mismatch on
        # the first forward.
        row_blocks, _raw_f = entset_segment_plan(f_segments, i_segments)
        block_caps = {
            _entset_logical_name(name): cap for name, cap, _n_float, _vocabs in row_blocks
        }

        def _check_block(logical: str, want: int, *, sliceable: bool = False) -> None:
            if logical not in block_caps:
                raise ValueError(
                    f"ActionLayout references row block {logical!r} but the "
                    f"encoder's segment plan has no such block (available: "
                    f"{sorted(block_caps)}).")
            cap = block_caps[logical]
            if sliceable:
                if want > cap:
                    raise ValueError(
                        f"ActionLayout wants {want} rows from block "
                        f"{logical!r} but that block only has {cap}.")
            elif want != cap:
                raise ValueError(
                    f"ActionLayout declares {want} rows for block "
                    f"{logical!r} but that block's real cap is {cap}.")

        if action_layout.play is not None:
            src, tgt, S, T = action_layout.play
            _check_block(src, S)
            _check_block(tgt, T)
        if action_layout.potion_pairs is not None:
            src, tgt, S_used, T = action_layout.potion_pairs
            _check_block(src, S_used, sliceable=True)
            _check_block(tgt, T)
        # pointer_blocks (whole-range replacements) and choice_row_overlays
        # (additive, offset INTO a row block) get the same construction-time
        # existence/cap check as play/potion_pairs above -- an undeclared
        # row block or an overlay that wants more rows than the block has is
        # a loud ValueError here, not a KeyError or a silent out-of-bounds
        # slice inside `action_logits`.
        for _base, width, row_block in action_layout.pointer_blocks:
            _check_block(row_block, width, sliceable=True)
        for _offset, n_slots, row_block, row_offset in action_layout.choice_row_overlays:
            if row_block not in block_caps:
                raise ValueError(
                    f"ActionLayout choice_row_overlays references row block "
                    f"{row_block!r} but the encoder's segment plan has no "
                    f"such block (available: {sorted(block_caps)}).")
            cap = block_caps[row_block]
            if row_offset < 0 or row_offset + n_slots > cap:
                raise ValueError(
                    f"ActionLayout choice_row_overlays entry wants rows "
                    f"[{row_offset}, {row_offset + n_slots}) from block "
                    f"{row_block!r} but that block only has {cap} rows.")

        # choice_float_overlays resolve against the encoder's own RAW
        # (unconsumed-by-any-row-block) float segments -- `entset_segment_
        # plan`'s second return value, already computed above as `_raw_f`.
        raw_f_widths = dict(_raw_f)

        def _float_overlay_names(prefix: str, n_slots: int) -> list[str]:
            # `f"{prefix}{k}"` for every k, EXCEPT the single-slot case
            # where the bare prefix is itself a real segment and no
            # indexed sibling exists (e.g. "shop.removal", which has no
            # "shop.removal0" -- unlike "map0".."map6").
            if n_slots == 1 and prefix in raw_f_widths and f"{prefix}0" not in raw_f_widths:
                return [prefix]
            return [f"{prefix}{k}" for k in range(n_slots)]

        self._choice_float_seg_names: list[list[str]] = []
        choice_float_seg_widths: list[int] = []
        for _offset, n_slots, prefix in action_layout.choice_float_overlays:
            names = _float_overlay_names(prefix, n_slots)
            widths = []
            for name in names:
                if name not in raw_f_widths:
                    raise ValueError(
                        f"ActionLayout choice_float_overlays prefix "
                        f"{prefix!r} resolves to segment {name!r}, which is "
                        f"not a raw float segment in this observation "
                        f"(available: {sorted(raw_f_widths)}).")
                widths.append(raw_f_widths[name])
            if len(set(widths)) != 1:
                raise ValueError(
                    f"ActionLayout choice_float_overlays prefix {prefix!r} "
                    f"spans segments of differing widths {widths} -- "
                    f"FloatPointerHead needs one shared width per entry.")
            self._choice_float_seg_names.append(names)
            choice_float_seg_widths.append(widths[0])

        # play_pair_feature_segments existence + width consistency --
        # `_validate_action_layout` already checked the tuple shape (empty,
        # or exactly 2 entries with `play` set); this checks the two names
        # actually resolve to `.f` segments (regardless of whether a row
        # block also consumes one of them, e.g. `enemies.f`) and that their
        # RAW widths are consistent with `play`'s (S, T) before wiring
        # `play_head`'s `pair_dim` -- a bad segment name or width mismatch
        # is a loud ValueError here, not a shape error deep inside
        # `play_pair_features` on the first forward.
        all_f_widths = dict(f_segments)
        self._play_pair_dim = 0
        if action_layout.play_pair_feature_segments:
            dm_name, enemy_f_name = action_layout.play_pair_feature_segments
            _src, _tgt, S, T = action_layout.play
            for name in (dm_name, enemy_f_name):
                if name not in all_f_widths:
                    raise ValueError(
                        f"ActionLayout play_pair_feature_segments names "
                        f"{name!r}, which is not a `.f` segment in this "
                        f"observation's f_segments (available: "
                        f"{sorted(all_f_widths)}).")
            if all_f_widths[dm_name] != S * T:
                raise ValueError(
                    f"ActionLayout play_pair_feature_segments' damage-matrix "
                    f"segment {dm_name!r} has width {all_f_widths[dm_name]}, "
                    f"not play's S*T ({S}*{T}={S * T}).")
            if all_f_widths[enemy_f_name] % T != 0:
                raise ValueError(
                    f"ActionLayout play_pair_feature_segments' enemy-preview "
                    f"segment {enemy_f_name!r} has width "
                    f"{all_f_widths[enemy_f_name]}, not a multiple of play's "
                    f"T ({T}).")
            n_enemy_float = all_f_widths[enemy_f_name] // T
            if n_enemy_float < _PLAY_PAIR_PREVIEW_SLICE.stop:
                raise ValueError(
                    f"ActionLayout play_pair_feature_segments' enemy-preview "
                    f"segment {enemy_f_name!r} has only {n_enemy_float} "
                    f"floats per row, fewer than the "
                    f"{_PLAY_PAIR_PREVIEW_SLICE.stop} the preview slice "
                    f"{_PLAY_PAIR_PREVIEW_SLICE} needs.")
            self._play_pair_dim = _PLAY_PAIR_DIM

        self._choice_width: int | None = None
        if action_layout.choice_base is not None:
            self._choice_width = next(
                (w for base, w in action_layout.positional if base == action_layout.choice_base),
                None)

        ctx_dim = self.hidden[-1] if self.hidden else self.actor_encoder.out_dim
        block_dim = self.actor_encoder.block_dim

        self.actor = _trunk(self.actor_encoder.out_dim, self.hidden)
        self.critic = _mlp(self.critic_encoder.out_dim, self.hidden, 1, out_std=1.0)

        # PairPointerHead/PointerHead/FloatPointerHead are imported lazily
        # -- action_heads.py imports `_layer_init` back from this module at
        # ITS top level, so an eager top-of-file import here (whichever
        # module a caller happens to import first) is a genuine circular
        # import; deferring it to call time sidesteps the ordering question
        # entirely (both modules are always fully loaded by the time any
        # model is constructed).
        from .action_heads import FloatPointerHead, PairPointerHead, PointerHead

        self.end_turn_head = None
        if action_layout.end_turn_index is not None:
            self.end_turn_head = _layer_init(neural_network.Linear(ctx_dim, 1), std=0.01)

        self.play_head = None
        if action_layout.play is not None:
            # `pair_dim` is 0 (no `pair=` argument at forward time) unless
            # play_pair_feature_segments is set.
            self.play_head = PairPointerHead(
                block_dim, block_dim, ctx_dim, pair_dim=self._play_pair_dim)

        self.potion_head = None
        if action_layout.potion_pairs is not None:
            # Potions have no damage matrix -- always pair_dim=0.
            self.potion_head = PairPointerHead(block_dim, block_dim, ctx_dim)

        self.positional_heads = neural_network.ModuleList([
            _layer_init(neural_network.Linear(ctx_dim, width), std=0.01)
            for _base, width in action_layout.positional
        ])

        # One PointerHead per pointer_blocks entry / choice_row_overlays
        # entry, and one FloatPointerHead per choice_float_overlays entry --
        # independent weights each (a relic row and a card row have
        # different projection semantics even at the same block_dim).
        self.pointer_heads = neural_network.ModuleList([
            PointerHead(block_dim, ctx_dim) for _base, _width, _row_block in action_layout.pointer_blocks
        ])
        self.choice_row_overlay_heads = neural_network.ModuleList([
            PointerHead(block_dim, ctx_dim) for _o, _n, _rb, _ro in action_layout.choice_row_overlays
        ])
        self.choice_float_overlay_heads = neural_network.ModuleList([
            FloatPointerHead(w, ctx_dim) for w in choice_float_seg_widths
        ])

        # v10 aux head (spec 2026-08-13-aux-hp-head-gae-lambda-design):
        # supervised "hp lost over the next 3 floors" prediction off the
        # critic/shared encoder. MUST stay registered LAST: Adam state is
        # positional; checkpoints.load_agent's aux-lenient overlay and
        # train_torch's optimizer-group patch both assume pre-existing
        # params keep their positions and aux params occupy the tail.
        self.aux_hp3_head = neural_network.Sequential(
            neural_network.Linear(self.critic_encoder.out_dim, 64), neural_network.Tanh(),
            neural_network.Linear(64, 1),
        )

    def get_value(self, obs: TensorObs) -> torch.Tensor:
        return self.critic(self.critic_encoder(obs)).squeeze(-1)

    def _choice_overlay(
        self, ctx: torch.Tensor, rows: dict[str, torch.Tensor], obs: TensorObs,
    ) -> torch.Tensor:
        """``(..., choice_width)`` additive overlay contribution for the
        CHOICE range, summed over every declared row/float overlay --
        factored out of ``action_logits`` so tests can inspect the overlay
        in isolation from the positional base score.

        Each overlay entry's per-slot scores are zero-padded out to
        ``choice_width`` at that entry's declared offset before summing --
        entries are independent (and, in practice, mutually exclusive per
        decision kind: presence gating makes every out-of-phase entry's
        contribution exactly 0), so a plain sum is correct even when two
        entries share an offset (e.g. REWARD_CARD and SHOP both start at
        slot 0).
        """
        assert self._choice_width is not None
        overlay = torch.zeros(
            *ctx.shape[:-1], self._choice_width, dtype=ctx.dtype, device=ctx.device)
        for head, (offset, n_slots, row_block, row_offset) in zip(
                self.choice_row_overlay_heads, self.action_layout.choice_row_overlays):
            src_rows = rows[row_block][..., row_offset:row_offset + n_slots, :]
            scores = head(src_rows, ctx)
            overlay = overlay + neural_functional.pad(
                scores, (offset, self._choice_width - offset - n_slots))
        for head, names, (offset, n_slots, _prefix) in zip(
                self.choice_float_overlay_heads, self._choice_float_seg_names,
                self.action_layout.choice_float_overlays):
            seg = torch.stack([self.actor_encoder.raw(obs, name) for name in names], dim=-2)
            scores = head(seg, ctx)
            overlay = overlay + neural_functional.pad(
                scores, (offset, self._choice_width - offset - n_slots))
        return overlay

    def action_logits(self, obs: TensorObs, mask: torch.Tensor) -> torch.Tensor:
        """Masked policy logits — same contract as
        ``MaskedActorCritic.action_logits``. Logits are assembled from the
        tied heads in ``action_layout`` order (end_turn, play, potion_pairs,
        then every positional/pointer_blocks range in ascending ``base``
        order -- a range can be either mechanism) and concatenated into
        one ``(..., n_actions)`` tensor before the illegal-action mask fill
        -- the tiling ``_validate_action_layout`` checked at construction is
        exactly what makes this concatenation land on ``n_actions`` wide.
        The CHOICE range (named by ``action_layout.choice_base``) gets its
        overlay contribution (``_choice_overlay``) added on top of its own
        positional score before being placed into that order."""
        pooled, rows = self.actor_encoder.encode(obs)
        ctx = self.actor(pooled)
        layout = self.action_layout

        parts: list[torch.Tensor] = []
        if layout.end_turn_index is not None:
            parts.append(self.end_turn_head(ctx))
        if layout.play is not None:
            src, tgt, S, T = layout.play
            pair = None
            if layout.play_pair_feature_segments:
                dm_name, enemy_f_name = layout.play_pair_feature_segments
                pair = self.actor_encoder.play_pair_features(obs, dm_name, enemy_f_name, S, T)
            parts.append(self.play_head(rows[src], rows[tgt], ctx, pair=pair))
        if layout.potion_pairs is not None:
            src, tgt, S_used, _T = layout.potion_pairs
            parts.append(self.potion_head(rows[src][..., :S_used, :], rows[tgt], ctx))

        # Tail: every `positional` and `pointer_blocks` range, in the SAME
        # ascending-`base` order `_validate_action_layout` tiled them in.
        tail = [("positional", i, base) for i, (base, _w) in enumerate(layout.positional)]
        tail += [("pointer", i, base) for i, (base, _w, _rb) in enumerate(layout.pointer_blocks)]
        tail.sort(key=lambda t: t[2])

        for kind, i, base in tail:
            if kind == "positional":
                out = self.positional_heads[i](ctx)
                if base == layout.choice_base and self._choice_width is not None:
                    out = out + self._choice_overlay(ctx, rows, obs)
                parts.append(out)
            else:
                _base, width, row_block = layout.pointer_blocks[i]
                parts.append(self.pointer_heads[i](rows[row_block][..., :width, :], ctx))

        logits = torch.cat(parts, dim=-1)
        return logits.masked_fill(~mask, _MASK_FILL)

    def _dist(self, obs: TensorObs, mask: torch.Tensor) -> Categorical:
        return Categorical(logits=self.action_logits(obs, mask))

    def get_action_and_value(
        self,
        obs: TensorObs,
        mask: torch.Tensor,
        action: torch.Tensor | None = None,
        with_aux: bool = False,
        with_dist: bool = False,
    ) -> tuple[torch.Tensor, ...]:
        """Returns ``(action, log_prob, entropy, value)`` — same contract as
        ``MaskedActorCritic.get_action_and_value`` — or, when
        ``with_aux=True`` (v10, spec 2026-08-13-aux-hp-head-gae-lambda-design),
        a 5-tuple ``(action, log_prob, entropy, value, aux_pred)`` with the
        aux head's "hp lost over the next 3 floors" prediction appended,
        computed off the SAME critic-encoder features as ``value`` (no extra
        encoder forward pass). When ``with_dist=True`` (v16), the already-
        built ``Categorical`` dist is appended as the FINAL tuple element,
        after ``aux_pred`` if ``with_aux`` is also set — the existing tuple
        orders never change, this only ever appends."""
        dist = self._dist(obs, mask)
        if action is None:
            action = dist.sample()
        cf = self.critic_encoder(obs)
        value = self.critic(cf).squeeze(-1)
        out = (action, dist.log_prob(action), dist.entropy(), value)
        if with_aux:
            out = out + (self.aux_hp3_head(cf).squeeze(-1),)
        if with_dist:
            out = out + (dist,)
        return out
