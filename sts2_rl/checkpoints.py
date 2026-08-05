"""Checkpoint construction shared by the trainer and the evaluator.

``train_torch.py`` saves arch-stamped checkpoints (``model``/``optim``/
``iteration``/``obs_dim``/``n_actions``/``hidden``/``arch``/``obs_schema``/
``env_kind``). Rebuilding the model those weights belong to needs the same
three decisions the trainer made — which env layout, which architecture, which
hidden sizes — so both sides go through this module rather than each keeping
its own copy of the construction rules.

A ``ModelSpec`` is that triple plus the env kind. The trainer builds one from
its CLI args; the evaluator builds one from the checkpoint's own stamps (see
``spec_from_checkpoint``), so a checkpoint always reloads into the
architecture it was trained as.

Env/run-scale imports are lazy: ``sts2_rl/__init__`` pulls this module in
through ``evaluation``, and importing ``run_env`` eagerly would drag greenlet
and the whole run layer into every ``import sts2_rl``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Envs whose observation/action layout is identical, so checkpoints move
# freely between them — that handoff IS the curriculum plan's phase 2.
RUN_SCALE_ENVS = frozenset({"run", "column"})


#: Recognised --arch values. An unrecognised arch must raise (T6 brief §4.1)
#: rather than silently falling through to MaskedActorCritic, the bug
#: make_model used to have.
ARCHS = frozenset({"mlp", "entity", "entset"})


@dataclass(frozen=True)
class ModelSpec:
    """Everything needed to build the model for one env, minus the env's own
    ``obs_dim``/``n_actions`` (which are measured from a live env)."""

    env_kind: str                       # combat | run | column
    card_obs: str = "hybrid"
    arch: str = "entset"                # mlp | entity | entset -- entset is
                                         # the only arch make_model still
                                         # builds against the v4/v7 envs
    hidden: tuple[int, ...] = (256, 256)
    shared_encoder: bool = False        # R10: entset only -- one shared
                                         # `_EntsetEncoder` instance for both
                                         # actor and critic instead of two
                                         # independent ones. Orthogonal to
                                         # `arch`/`ENTSET_HEAD_VERSION`: it
                                         # changes which encoder object gets
                                         # constructed, not the head
                                         # structure, so it is stamped and
                                         # checked as its own field rather
                                         # than folded into the head-version
                                         # bump (see check_checkpoint below).


def obs_schema_version(spec: ModelSpec) -> int:
    """The schema version stamped into / checked against checkpoints — combat
    and run-scale envs version their layouts independently (run and column
    share one layout, hence one version)."""
    if spec.env_kind in RUN_SCALE_ENVS:
        from .run_env import RUN_OBS_SCHEMA_VERSION

        return RUN_OBS_SCHEMA_VERSION
    from .full_env import OBS_SCHEMA_VERSION

    return OBS_SCHEMA_VERSION


def model_obs_layout(spec: ModelSpec) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """This env's ``(f_segments, i_segments)`` — the v4 ``{"f", "i"}``
    layout ``--arch entset`` slices by (T6 brief §4.3). The run-scale envs'
    own ``run_obs_layout`` already folds the trailing combat block in under
    a ``"combat."`` prefix (``sts2_rl.run_env``), so this just picks the
    right layout function and hands back its two segment lists."""
    if spec.env_kind in RUN_SCALE_ENVS:
        from .run_env import run_obs_layout

        layout = run_obs_layout(spec.card_obs)
    else:
        from .full_env import combat_obs_layout

        layout = combat_obs_layout(spec.card_obs)
    return layout.f_segments, layout.i_segments


def model_obs_segments(spec: ModelSpec) -> list[tuple[str, int]]:
    """The named (segment, width) layout ``--arch entity`` slices by:
    ``model_obs_layout``'s two halves concatenated ``f_segments +
    i_segments`` (the same order ``models._as_flat`` flattens a
    :class:`~sts2_rl.tensor_obs.TensorObs` in, so the two stay in sync).

    ``entity`` is frozen at its v3-era, flat-``Box`` design
    (``models._segment_plan``'s name-suffix-plus-width matching) — against
    the v4 layout's names/widths almost nothing matches, so this
    degenerates to raw float pass-through (no embeddings), which is the
    deliberate, documented outcome for the two frozen archs (see
    ``models.py``'s module docstring) rather than something this function
    needs to fix.
    """
    f_segments, i_segments = model_obs_layout(spec)
    return f_segments + i_segments


#: The schema version at which each env's observation became the "f"/"i"
#: Dict generation (the entity-obs-schema.md rewrite that made ``mlp``/
#: ``entity`` unsafe -- see ``make_model``): combat's Dict rewrite landed at
#: schema 4, run-scale's (run/column share one layout) at schema 7.
#:
#: This used to be a ``frozenset({4, 7})`` literal enumerating "the known-bad
#: versions" -- the exact shape of guard this project keeps getting bitten
#: by: it checked membership in a fixed set, so the very next schema bump
#: (5, 8, ...) fell outside the set and the refusal went silent without a
#: single line changing at the call site. A checkpoint-format schema number
#: can only go up (``check_checkpoint``'s schema check refuses anything that
#: doesn't match exactly, and nothing in this codebase ever decrements
#: ``OBS_SCHEMA_VERSION``/``RUN_OBS_SCHEMA_VERSION``), so "is this env still
#: on the unsafe Dict generation" is exactly "is its current schema version
#: >= the version that generation started at" -- a threshold, not a
#: membership test. Every later bump is automatically >= the threshold, so
#: the refusal cannot lapse just because a number changed elsewhere;
#: ``test_make_model_refuses_future_v4_generation_schema`` in test_models.py
#: pins that property directly by simulating a future bump.
_V4_GENERATION_MIN_SCHEMA = {
    "combat": 4,
    "run": 7,
    "column": 7,
}


def _is_v4_generation(spec: ModelSpec) -> bool:
    """Whether ``spec``'s env is still on the "f"/"i" Dict generation that
    ``mlp``/``entity`` cannot safely train against (see the threshold map's
    docstring above) -- true at the generation's starting schema and at
    every schema after it, by construction."""
    threshold = _V4_GENERATION_MIN_SCHEMA.get(spec.env_kind)
    if threshold is None:
        raise SystemExit(
            f"no v4-generation schema threshold recorded for env_kind "
            f"{spec.env_kind!r}; add one to _V4_GENERATION_MIN_SCHEMA rather "
            f"than silently skipping the mlp/entity refusal.")
    return obs_schema_version(spec) >= threshold


def make_model(spec: ModelSpec, obs_dim: tuple[int, int], n_actions: int):
    """Build the spec's architecture for an env of this shape.

    ``obs_dim`` is always the env's own ``(f_dim, i_dim)`` pair (T6 brief
    §1/§4) — ``mlp``/``entity`` sum it to the flat width their frozen
    designs expect; ``entset`` uses it directly. An unrecognised ``arch``
    raises rather than silently building a ``MaskedActorCritic`` (T6 brief
    §4.1 — this used to fall through silently for anything other than
    ``"entity"``).

    ``mlp``/``entity`` are refused outright against the v4/v7 ``{f, i}``
    generation (final fix-pass review item 2): ``models._as_flat`` feeds
    both of them ``concat(f, i.float())`` with no normalization, so
    unnormalized vocabulary ids up to 640 sit beside floats bounded in
    ``[0,1]`` going into an orthogonal-init ``Linear`` — measured, not just
    "degenerate": the id magnitudes dwarf the ~1400 genuinely numeric
    features. This project keeps no old-vs-new comparison baseline by
    explicit decision, so there is no legitimate reason left to build either
    architecture against these envs — the same "must raise, not silently
    degrade" rule already applied to an unrecognised ``arch`` name. The
    classes themselves are untouched: they stay correct for the frozen flat
    contract, exercised directly (not through this factory) by their own
    unit tests.
    """
    from .models import EntitySetActorCritic, EntityActorCritic, MaskedActorCritic

    f_dim, i_dim = obs_dim
    flat_dim = f_dim + i_dim

    if spec.arch in ("mlp", "entity") and _is_v4_generation(spec):
        raise SystemExit(
            f"--arch {spec.arch} is refused against env_kind {spec.env_kind!r} "
            f"(obs schema {obs_schema_version(spec)}, the v4/v7 {{f, i}} "
            f"generation): concat(f, i) puts raw, unnormalized vocabulary ids "
            f"(up to 640) beside floats bounded in [0,1] into the same "
            f"orthogonal-init Linear -- the id magnitudes swamp the numeric "
            f"half rather than merely degrading it, and this project keeps no "
            f"old-vs-new comparison baseline. Use --arch entset.")

    if spec.arch == "entset":
        f_segments, i_segments = model_obs_layout(spec)
        seg_f = sum(w for _, w in f_segments)
        seg_i = sum(w for _, w in i_segments)
        if (seg_f, seg_i) != (f_dim, i_dim):   # layout drift between env and segment map
            raise SystemExit(
                f"segment layout sums to (f={seg_f}, i={seg_i}) but the env "
                f"emits (f={f_dim}, i={i_dim}); model_obs_layout is out of "
                f"sync with the env.")
        # T7 brief (tied action head): the combat env's block gets a pointer
        # layout over hand/enemies/potion rows; the run-scale envs' embedded
        # combat block gets the SAME pointer layout (sized to the belt's
        # true worst case, MAX_POTION_SLOTS) plus positional CHOICE/SELECT/
        # belt-POTION ranges. Nothing else about this factory's guards
        # changes.
        from .models import combat_action_layout, run_action_layout

        if spec.env_kind in RUN_SCALE_ENVS:
            action_layout = run_action_layout()
        else:
            from .full_env import MAX_POTIONS

            action_layout = combat_action_layout(MAX_POTIONS)
        return EntitySetActorCritic(
            f_segments, i_segments, n_actions, action_layout,
            hidden=tuple(spec.hidden), shared_encoder=spec.shared_encoder)
    if spec.arch == "entity":
        segments = model_obs_segments(spec)
        seg_dim = sum(w for _, w in segments)
        if seg_dim != flat_dim:   # layout drift between env and segment map
            raise SystemExit(
                f"segment layout sums to {seg_dim} floats but the env emits "
                f"{flat_dim}; model_obs_segments is out of sync with the env.")
        model = EntityActorCritic(segments, n_actions, hidden=tuple(spec.hidden))
        # Overwritten to the env's own pair, not read anywhere in forward()
        # (the trunk's Linear was already built from flat_dim above) — this
        # is purely so checkpoint_payload's "obs_dim" and check_checkpoint's
        # shape comparison stay in the ONE (f_dim, i_dim) currency every
        # arch shares, instead of entset's pair vs mlp/entity's flat int.
        model.obs_dim = obs_dim
        return model
    if spec.arch == "mlp":
        model = MaskedActorCritic(flat_dim, n_actions, hidden=tuple(spec.hidden))
        model.obs_dim = obs_dim   # see the comment in the "entity" branch above
        return model
    raise SystemExit(
        f"unrecognised --arch {spec.arch!r}; choose one of {sorted(ARCHS)}.")


def check_checkpoint(ckpt: dict, spec: ModelSpec,
                     obs_dim: tuple[int, int], n_actions: int) -> None:
    """Refuse a checkpoint that doesn't match this env/schema/model, with a
    clear message instead of a cryptic load_state_dict error."""
    ckpt_kind = ckpt.get("env_kind", "combat")
    if ckpt_kind != spec.env_kind and not (
            {ckpt_kind, spec.env_kind} <= RUN_SCALE_ENVS):
        # Phrased for both callers: the trainer's fix is usually --fresh or a
        # different --save/--resume, the evaluator's is a different --env.
        raise SystemExit(
            f"checkpoint was trained on the {ckpt_kind!r} env, "
            f"this run uses {spec.env_kind!r}; pass a matching checkpoint, "
            f"change --env, or (training) start --fresh.")
    if ckpt_kind != spec.env_kind:
        print(f"Curriculum handoff: continuing a {ckpt_kind!r}-env checkpoint "
              f"on the {spec.env_kind!r} env.")
    if ckpt.get("obs_schema") != obs_schema_version(spec):
        # Phase 1 of the entity-obs-schema work rewrote the observation from
        # a flat array to an "f"/"i" Dict — a different Gym space type, not a
        # reshape of the same array — so there is deliberately NO migration
        # onto the current schema for any older checkpoint, including the
        # v3->v4 and v5->v6 hops this hint used to point at (both migration
        # tools are unreachable dead code now; see migrate_checkpoint and
        # migrate_checkpoint_actions). Every stale schema dead-ends here.
        raise SystemExit(
            f"checkpoint obs schema {ckpt.get('obs_schema')} != current "
            f"{obs_schema_version(spec)}; this schema bump has no migration "
            f"path — start training over with --fresh.")
    ckpt_arch = ckpt.get("arch", "mlp")   # pre-stamp checkpoints are all MLP
    if ckpt_arch != spec.arch:
        raise SystemExit(
            f"checkpoint arch {ckpt_arch!r} != this run's --arch {spec.arch!r}; "
            f"there is no weight migration between architectures — pick the "
            f"matching --arch or start --fresh.")
    if ckpt_arch == "entset":
        # T7 (tied action head): the entset head's parameter STRUCTURE
        # changed in place -- same arch string, same (obs_dim, n_actions,
        # hidden) triple -- so a stale checkpoint would otherwise sail past
        # every check above and die inside `load_state_dict` with a raw key
        # error instead of an honest refusal (this project's recorded rule:
        # the version gate must catch this, a shape/key mismatch is only the
        # fallback -- ledger, round-2 gap 3). Checked BEFORE the shape
        # comparison below so a checkpoint that is ALSO shape-stale still
        # gets the true reason first. mlp/entity payloads never carry this
        # key and are refused earlier (arch mismatch or the v4-generation
        # guard), so this branch never fires for them.
        from . import models

        ckpt_head_version = ckpt.get("head_version", 1)   # pre-stamp = version 1
        if ckpt_head_version != models.ENTSET_HEAD_VERSION:
            raise SystemExit(
                f"checkpoint head_version {ckpt_head_version} != current "
                f"{models.ENTSET_HEAD_VERSION}; this checkpoint predates the "
                f"phase-2 tied action head -- there is no weight migration "
                f"for it, start training over with --fresh.")
        # R10: `shared_encoder` changes whether the checkpoint's state_dict
        # has ONE `actor_encoder.*` key set (critic_encoder shares it) or
        # TWO independent `actor_encoder.*`/`critic_encoder.*` sets -- a
        # structural difference `load_state_dict` would otherwise surface as
        # a cryptic missing/unexpected-key error rather than the honest
        # refusal this project's checkpoint gate is supposed to give (same
        # "the version gate must catch this, a shape/key mismatch is only
        # the fallback" rule as `head_version` above). This is a SEPARATE
        # stamp, not folded into `ENTSET_HEAD_VERSION` -- the flag is
        # orthogonal to the tied action head's structure, it only changes
        # which encoder OBJECT the actor and critic point at. Missing key =
        # False (pre-R10 checkpoints were all built with two independent
        # encoders).
        ckpt_shared_encoder = ckpt.get("shared_encoder", False)
        if ckpt_shared_encoder != spec.shared_encoder:
            raise SystemExit(
                f"checkpoint shared_encoder={ckpt_shared_encoder} != this "
                f"run's --shared-encoder={spec.shared_encoder}; the actor "
                f"and critic encoders are structurally different objects "
                f"between the two arms (one shared instance vs two "
                f"independent ones) -- there is no weight migration between "
                f"them, match --shared-encoder or start --fresh.")
    shape = (ckpt.get("obs_dim"), ckpt.get("n_actions"), tuple(ckpt.get("hidden", ())))
    want = (obs_dim, n_actions, tuple(spec.hidden))
    if shape != want:
        raise SystemExit(
            f"checkpoint architecture {shape} != this run's {want} "
            f"(obs_dim, n_actions, hidden); can't resume — match --hidden or use --fresh.")


def spec_from_checkpoint(ckpt: dict, env_kind: str,
                         card_obs: str = "hybrid") -> ModelSpec:
    """The spec a saved checkpoint describes, evaluated against ``env_kind``.

    ``arch``/``hidden`` come from the checkpoint (loading adopts the
    architecture the weights were trained as); ``env_kind``/``card_obs``
    describe the env it is about to be run on, so ``check_checkpoint`` still
    catches an env or schema mismatch.
    """
    return ModelSpec(
        env_kind=env_kind,
        card_obs=card_obs,
        arch=ckpt.get("arch", "mlp"),
        hidden=tuple(ckpt.get("hidden", ())),
        shared_encoder=ckpt.get("shared_encoder", False),
    )


# ── v3 → v4 migration (run.boss.identity + run.map.grid/meta) ────────────


def migrate_checkpoint(ckpt: dict, card_obs: str = "hybrid") -> dict:
    """Migrate a v3 run-scale checkpoint (either arch) to obs schema v4.

    Function-preserving: the v4 segments are pure feature additions, so the
    first trunk layer of each head gets zero columns spliced in at their
    positions (and the matching Adam moments get the same splice, with zero
    moments — exact for fresh weights). The migrated model computes
    bit-identical logits and values; continued training grows into the new
    inputs. All other weights are untouched. For ``--arch entity`` no
    embedding parameters change: ``run.boss.identity`` reuses the shared
    monsters table the combat block already trained.

    Returns a new checkpoint dict (the input is not mutated) with updated
    ``obs_dim``/``obs_schema`` stamps.

    UNREACHABLE as of the phase-1 schema bump (entity-obs-schema.md):
    ``check_checkpoint`` now refuses every pre-v7 checkpoint before this
    function could ever be called, and phase 1 rewrote the run observation
    from a flat array to an ``"f"``/``"i"`` Dict — a different Gym space
    type, not a reshape the old column-splice technique could target even in
    principle. Kept per CLAUDE.md §3 (this module doesn't delete
    pre-existing code it didn't write); its env-kind/schema guards below
    still behave exactly as designed, but a well-formed v3 checkpoint now
    hits an explicit ``SystemExit`` instead of running the (impossible)
    migration.
    """
    env_kind = ckpt.get("env_kind", "combat")
    if env_kind not in RUN_SCALE_ENVS:
        raise SystemExit(
            f"the v3 → v4 migration covers run-scale checkpoints only; this "
            f"one was trained on the {env_kind!r} env.")
    if ckpt.get("obs_schema") != 3:
        raise SystemExit(
            f"can only migrate obs schema 3 → 4; checkpoint has schema "
            f"{ckpt.get('obs_schema')}.")
    # Everything past this point built a v4 flat-array checkpoint by splicing
    # zero columns into a v3 flat-array one — a technique with no target: the
    # phase-1 bump replaced run_obs_segments with run_obs_segments_f/_i and
    # made the run observation a Dict, not a wider flat array. There is no
    # schema this function can still migrate a well-formed input onto, so say
    # that plainly instead of letting `from .run_env import run_obs_segments`
    # raise a stale ImportError.
    raise SystemExit(
        "the v3 -> v4 migration is unreachable: the phase-1 schema bump "
        "(entity-obs-schema.md) replaced the flat run observation with an "
        "\"f\"/\"i\" Dict, so there is no schema left for this checkpoint to "
        "migrate onto — start training over with --fresh.")


# ── v5 → v6 migration (the out-of-combat potion action block) ────────────

def migrate_checkpoint_actions(ckpt: dict, card_obs: str = "hybrid") -> dict:
    """Migrate a v5 run-scale checkpoint to the v6 ACTION layout (either arch).

    v6 changes no observation at all — it appends a MAX_POTION_SLOTS-wide
    out-of-combat potion block at the END of the action layout
    (``run_env.POTION_BASE``), so every pre-existing action keeps its index.
    Migration therefore appends zero rows to the policy head and its Adam
    moments and touches nothing else: the whole critic, both trunks and (for
    the entity arch) every embedding table are carried over bit-for-bit.

    Function-preserving where it can be. The value function is exactly
    preserved, and so are the policy's logits over the old actions — so in
    every state the old policy could reach while holding no AnyTime potion (the
    new block masked off) the migrated model is bit-identical. Where a belt
    potion *is* drinkable the new action enters at logit 0, which is the
    neutral prior for an option the old policy never had; no weight could
    encode a preference it was never able to express.

    Returns a new checkpoint dict (the input is not mutated) with updated
    ``n_actions``/``obs_schema`` stamps.

    UNREACHABLE as of the phase-1 schema bump (entity-obs-schema.md):
    ``check_checkpoint`` now refuses every pre-v7 checkpoint before this
    function could ever be called, and ``RUN_OBS_SCHEMA_VERSION`` moved to 7
    without this function's target ever becoming buildable again — v6 was a
    flat-array action-layout tweak, and phase 1 replaced the flat run
    observation with an ``"f"``/``"i"`` Dict, so "grow the v5 checkpoint
    onto v6" no longer names a schema this repo produces. Kept per CLAUDE.md
    §3; its env-kind/schema/shape guards below still behave exactly as
    designed, but a well-formed v5 checkpoint now hits an explicit
    ``SystemExit`` instead of the stale ``assert RUN_OBS_SCHEMA_VERSION ==
    6``.
    """
    env_kind = ckpt.get("env_kind", "combat")
    if env_kind not in RUN_SCALE_ENVS:
        raise SystemExit(
            f"the v5 -> v6 migration covers run-scale checkpoints only; this "
            f"one was trained on the {env_kind!r} env.")
    if ckpt.get("obs_schema") != 5:
        raise SystemExit(
            f"can only migrate obs schema 5 -> 6; checkpoint has schema "
            f"{ckpt.get('obs_schema')}.")
    # The honest raise comes FIRST, ahead of any shape check on the
    # checkpoint's ACTUAL n_actions (fix-pass correction, review item 3):
    # this migration's target no longer exists for ANY well-formed input, so
    # there is nothing left a shape check could usefully gate -- and the
    # obvious-looking "does it match the v5 width" check that used to sit
    # here computed that width from TODAY's `N_ACTIONS - MAX_POTION_SLOTS`,
    # which is today's formula, not the historical v5 one (MAX_POTION_SLOTS
    # itself grew 4 -> 10 after v5 shipped). That stale check meant a
    # genuine v5 checkpoint could be told "it doesn't match the layout this
    # migration grows" instead of the true reason: there is no migration
    # path at all.
    raise SystemExit(
        "the v5 -> v6 action migration is unreachable: the phase-1 schema "
        "bump (entity-obs-schema.md) moved RUN_OBS_SCHEMA_VERSION past 6 "
        "without this migration's v6 flat-action target ever being rebuilt, "
        "so there is no schema left for this checkpoint to migrate onto — "
        "start training over with --fresh.")


def load_agent(path: str, *, env_kind: str, obs_dim: tuple[int, int], n_actions: int,
               card_obs: str = "hybrid", device: str = "cpu") -> tuple[Any, dict]:
    """Load a ``train_torch.py`` checkpoint into an eval-mode model.

    ``obs_dim`` is the env's ``(f_dim, i_dim)`` pair (T6 brief §5) — every
    arch's checkpoint stamps its ``obs_dim`` in that same currency now (see
    ``make_model``), so this needs no arch-specific branching.

    Dispatches on the checkpoint's ``arch`` stamp, refuses an env/schema/shape
    mismatch through ``check_checkpoint``, and never writes to ``path``.
    Returns ``(model, ckpt)`` — the raw checkpoint dict comes along so callers
    can report its iteration/provenance.
    """
    import torch

    ckpt = torch.load(path, map_location=device, weights_only=False)
    spec = spec_from_checkpoint(ckpt, env_kind, card_obs)
    check_checkpoint(ckpt, spec, obs_dim, n_actions)
    model = make_model(spec, obs_dim, n_actions).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model, ckpt
