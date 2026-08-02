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
  ``{"f", "i"}`` observation's own architecture (OBS_SCHEMA.md §2.2, T6
  brief §4): a masked sum-pool of per-row embeddings over each ``.ids``
  block, using the id/float pair directly rather than a flat-obs slice.
  ``mlp``/``entity`` still work against the new envs (T6 brief §4.1) — they
  just see a flattened ``concat(f, i)`` with ids as plain numbers, no
  embedding, which is a deliberate degeneration, not a bug: they are the
  frozen v3-era archs, and ``entset`` is the schema-v4 replacement.

``train_torch.py`` and the env stay put when architectures change, because the
PPO loop only depends on ``get_value`` / ``get_action_and_value``. Those two
methods accept either a plain flat ``torch.Tensor`` (the historical contract,
still used directly by unit tests) or a
:class:`~sts2_rl.tensor_obs.TensorObs` (what the real training loop now
passes uniformly, regardless of arch) — ``mlp``/``entity`` flatten the
latter via ``_as_flat``; ``entset`` consumes it directly.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as neural_network
from torch.distributions import Categorical

from .full_env import MAX_ENEMIES
from .tensor_obs import TensorObs
from .vocab import CAPACITIES

# Illegal-action logit floor. Large enough that softmax gives ~0 probability,
# finite so log_prob / entropy never produce NaNs (the env guarantees at least
# one legal action per row, so a fully-masked row shouldn't occur anyway).
_MASK_FILL = -1e8


def _as_flat(obs: torch.Tensor | TensorObs) -> torch.Tensor:
    """``mlp``/``entity``'s half of the T6 bridge: they keep the pre-v4 flat-
    tensor contract, so a :class:`TensorObs` (what the real training loop
    now passes uniformly, T6 brief §4.1) is flattened to
    ``concat(f, i.float())`` before it reaches either architecture's first
    ``Linear``. A plain ``torch.Tensor`` (every direct unit-test call site)
    passes straight through unchanged. This is a deliberate degeneration,
    not a bug to fix: ids become plain numbers with no embedding, because
    ``mlp``/``entity`` are the frozen v3-era archs and ``entset`` is the
    schema-v4 replacement (see the module docstring)."""
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
# row per entity instance rather than one dict slot per id (T6 brief §4.2).

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

# The explicit segment -> per-int-field vocabulary map T6 brief §4.3 asks
# for, replacing _segment_plan's name-suffix-plus-width-match inference
# (which stays as EntityActorCritic's own, frozen, v3-era mechanism — see
# that class). Keyed by the LOGICAL block name: an ``.ids`` segment name
# with any leading run-env "combat." prefix and the trailing ".ids" both
# stripped, so one entry covers a segment whether it's read from
# ``full_env.combat_obs_layout()`` directly (--env combat) or folded into
# ``run_env.run_obs_layout()`` under the "combat." prefix (--env run/column).
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
    # run_env.py's T5a MAX_OBS_ID check).
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

    This is also the completeness check T6 brief §4.3 asks for: called
    against both envs' REAL layouts (as the model-construction path does),
    an undeclared ``.ids`` segment or a width that doesn't divide evenly
    raises immediately — see ``test_tensor_obs.py``'s sibling,
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
    """The provisional entset encoder (T6 brief §4.2) — "masked sum/mean plus
    per-field projections", the phase-2 plan's own stated starting point,
    not the tied action head phase 2 builds.

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

        i_slices = _slices(i_segments)
        f_slices = _slices(f_segments)
        self._blocks: neural_network.ModuleList = neural_network.ModuleList()
        self._block_meta: list[dict] = []
        self.out_spans: dict[str, tuple[int, int]] = {}
        out_dim = 0
        for name, cap, n_float, vocabs in row_blocks:
            n_int = len(vocabs)
            row_in = sum(1 if v is None else dims[v] for v in vocabs) + n_float
            proj = _layer_init(neural_network.Linear(row_in, block_dim))
            self._blocks.append(proj)
            primary = next(idx for idx, v in enumerate(vocabs) if v is not None)
            f_name = f"{name[:-len('.ids')]}.f"
            self._block_meta.append(dict(
                i_slice=i_slices[name],
                f_slice=f_slices.get(f_name),
                cap=cap, n_int=n_int, n_float=n_float,
                vocabs=vocabs, primary=primary,
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

    def forward(self, obs: TensorObs) -> torch.Tensor:
        f, i = obs.f, obs.i
        parts: list[torch.Tensor] = []
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
            parts.append((projected * mask).sum(dim=-2))
        for name, sl in self._raw_slices:
            parts.append(f[..., sl])
        return torch.cat(parts, dim=-1)


class EntitySetActorCritic(neural_network.Module):
    """``--arch entset`` — the schema-v4 architecture (module docstring;
    OBS_SCHEMA.md §2.2, T6 brief §4). Same masked-categorical policy contract
    as the other two archs (separate actor/critic trunks AND encoders); the
    one difference is that ``obs`` here is a
    :class:`~sts2_rl.tensor_obs.TensorObs`, not a flat tensor — the encoder
    needs both halves together to embed by id and attach that id's floats.
    """

    arch = "entset"

    def __init__(
        self,
        f_segments: list[tuple[str, int]],
        i_segments: list[tuple[str, int]],
        n_actions: int,
        hidden: tuple[int, ...] = (256, 256),
        embed_dims: dict[str, int] | None = None,
    ) -> None:
        super().__init__()
        self.f_segments = list(f_segments)
        self.i_segments = list(i_segments)
        f_dim = sum(w for _, w in f_segments)
        i_dim = sum(w for _, w in i_segments)
        self.obs_dim = (f_dim, i_dim)
        self.n_actions = n_actions
        self.hidden = tuple(hidden)
        self.actor_encoder = _EntsetEncoder(f_segments, i_segments, embed_dims)
        self.critic_encoder = _EntsetEncoder(f_segments, i_segments, embed_dims)
        self.actor = _mlp(self.actor_encoder.out_dim, self.hidden, n_actions, out_std=0.01)
        self.critic = _mlp(self.critic_encoder.out_dim, self.hidden, 1, out_std=1.0)

    def get_value(self, obs: TensorObs) -> torch.Tensor:
        return self.critic(self.critic_encoder(obs)).squeeze(-1)

    def action_logits(self, obs: TensorObs, mask: torch.Tensor) -> torch.Tensor:
        """Masked policy logits — same contract as
        ``MaskedActorCritic.action_logits``."""
        return self.actor(self.actor_encoder(obs)).masked_fill(~mask, _MASK_FILL)

    def _dist(self, obs: TensorObs, mask: torch.Tensor) -> Categorical:
        return Categorical(logits=self.action_logits(obs, mask))

    def get_action_and_value(
        self,
        obs: TensorObs,
        mask: torch.Tensor,
        action: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns ``(action, log_prob, entropy, value)`` — same contract as
        ``MaskedActorCritic.get_action_and_value``."""
        dist = self._dist(obs, mask)
        if action is None:
            action = dist.sample()
        return action, dist.log_prob(action), dist.entropy(), self.get_value(obs)
