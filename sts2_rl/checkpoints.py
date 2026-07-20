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


@dataclass(frozen=True)
class ModelSpec:
    """Everything needed to build the model for one env, minus the env's own
    ``obs_dim``/``n_actions`` (which are measured from a live env)."""

    env_kind: str                       # combat | run | column
    card_obs: str = "hybrid"
    arch: str = "mlp"                   # mlp | entity
    hidden: tuple[int, ...] = (256, 256)


def obs_schema_version(spec: ModelSpec) -> int:
    """The schema version stamped into / checked against checkpoints — combat
    and run-scale envs version their layouts independently (run and column
    share one layout, hence one version)."""
    if spec.env_kind in RUN_SCALE_ENVS:
        from .run_env import RUN_OBS_SCHEMA_VERSION

        return RUN_OBS_SCHEMA_VERSION
    from .full_env import OBS_SCHEMA_VERSION

    return OBS_SCHEMA_VERSION


def model_obs_segments(spec: ModelSpec) -> list[tuple[str, int]]:
    """The named (segment, width) layout of this env's observation — what the
    entity model slices by. The run-scale envs report their trailing combat
    block as one opaque segment, so expand it into the combat layout here."""
    from .full_env import obs_segments

    combat = obs_segments(spec.card_obs)
    if spec.env_kind in RUN_SCALE_ENVS:
        from .run_env import run_obs_segments

        return run_obs_segments(spec.card_obs) + [
            (f"combat.{name}", width) for name, width in combat]
    return combat


def make_model(spec: ModelSpec, obs_dim: int, n_actions: int):
    """Build the spec's architecture for an env of this shape."""
    from .models import EntityActorCritic, MaskedActorCritic

    if spec.arch == "entity":
        segments = model_obs_segments(spec)
        seg_dim = sum(w for _, w in segments)
        if seg_dim != obs_dim:   # layout drift between env and segment map
            raise SystemExit(
                f"segment layout sums to {seg_dim} floats but the env emits "
                f"{obs_dim}; model_obs_segments is out of sync with the env.")
        return EntityActorCritic(segments, n_actions, hidden=tuple(spec.hidden))
    return MaskedActorCritic(obs_dim, n_actions, hidden=tuple(spec.hidden))


def check_checkpoint(ckpt: dict, spec: ModelSpec,
                     obs_dim: int, n_actions: int) -> None:
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
        hint = " the observation layout changed — retrain."
        if (ckpt.get("obs_schema") == 3 and obs_schema_version(spec) == 4
                and spec.env_kind in RUN_SCALE_ENVS):
            hint = (" v3 → v4 only added features, so a lossless migration "
                    "exists: py migrate_ckpt.py <this checkpoint> <new path>.")
        raise SystemExit(
            f"checkpoint obs schema {ckpt.get('obs_schema')} != current "
            f"{obs_schema_version(spec)};" + hint)
    ckpt_arch = ckpt.get("arch", "mlp")   # pre-stamp checkpoints are all MLP
    if ckpt_arch != spec.arch:
        raise SystemExit(
            f"checkpoint arch {ckpt_arch!r} != this run's --arch {spec.arch!r}; "
            f"there is no weight migration between architectures — pick the "
            f"matching --arch or start --fresh.")
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
    )


# ── v3 → v4 migration (run.boss.identity + run.map.grid/meta) ────────────

# The run-obs segments added by schema v4. Everything the migration does is
# derived from these names against the current layout — no hardcoded offsets.
_V4_NEW_SEGMENTS = frozenset({"run.boss.identity", "run.map.grid", "run.map.meta"})


def _segment_out_width(name: str, width: int) -> int:
    """A segment's width in _SegmentEncoder *output* space: raw pieces pass
    through, vocabulary pieces contract to their embedding dim."""
    from .models import EMBED_DIMS, _segment_plan

    total = 0
    for kind, w in _segment_plan(name, width):
        total += w if kind == "raw" else EMBED_DIMS["cards" if kind == "cards2" else kind]
    return total


def _new_column_blocks(segments, width_fn) -> list[tuple[int, int]]:
    """Where the v4 segments land as first-layer input columns: (position in
    the OLD column space, width) per new segment, ascending. ``width_fn``
    picks the space — flat obs (mlp trunks) or encoder output (entity)."""
    blocks: list[tuple[int, int]] = []
    old_off = 0
    for name, width in segments:
        w = width_fn(name, width)
        if name in _V4_NEW_SEGMENTS:
            blocks.append((old_off, w))
        else:
            old_off += w
    return blocks


def _splice_zero_columns(mat, blocks: list[tuple[int, int]]):
    """Insert zero column-blocks into a 2-D tensor at the given old-space
    positions. Old columns keep their values and order."""
    import torch

    pieces = []
    prev = 0
    for pos, width in blocks:
        pieces.append(mat[:, prev:pos])
        pieces.append(mat.new_zeros(mat.shape[0], width))
        prev = pos
    pieces.append(mat[:, prev:])
    return torch.cat(pieces, dim=1)


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
    """
    import copy

    from .run_env import RUN_OBS_SCHEMA_VERSION, run_obs_segments

    env_kind = ckpt.get("env_kind", "combat")
    if env_kind not in RUN_SCALE_ENVS:
        raise SystemExit(
            f"the v3 → v4 migration covers run-scale checkpoints only; this "
            f"one was trained on the {env_kind!r} env.")
    if ckpt.get("obs_schema") != 3:
        raise SystemExit(
            f"can only migrate obs schema 3 → 4; checkpoint has schema "
            f"{ckpt.get('obs_schema')}.")
    assert RUN_OBS_SCHEMA_VERSION == 4, "migration written for the v4 layout"

    segments = run_obs_segments(card_obs)
    added = sum(w for n, w in segments if n in _V4_NEW_SEGMENTS)
    new_obs_dim = ckpt["obs_dim"] + added
    spec = spec_from_checkpoint(ckpt, env_kind, card_obs)
    # Also validates the segment layout against the env (and would catch a
    # card_obs mismatch for entity checkpoints via its seg-sum check).
    model = make_model(spec, new_obs_dim, ckpt["n_actions"])

    width_fn = _segment_out_width if spec.arch == "entity" else (lambda n, w: w)
    blocks = _new_column_blocks(segments, width_fn)
    grown = sum(w for _, w in blocks)

    new_ckpt = copy.deepcopy(ckpt)
    state = new_ckpt["model"]
    # Adam state is keyed by position in the (single) param group, which is
    # named_parameters() order — and for the entity arch that ORDER changed:
    # run.boss.identity makes the encoder create the shared monsters table
    # earlier in the segment walk than the v3 layout did (it used to first
    # appear in the combat block). Same names, same shapes, different
    # positions — so remap the saved per-param state from the v3 order to
    # the v4 order before touching anything, or moments cross-attach.
    param_names = [n for n, _ in model.named_parameters()]
    if spec.arch == "entity":
        from .models import EntityActorCritic

        old_segments = [(n, w) for n, w in model_obs_segments(spec)
                        if n not in _V4_NEW_SEGMENTS]
        old_model = EntityActorCritic(old_segments, ckpt["n_actions"],
                                      hidden=tuple(spec.hidden))
        old_names = [n for n, _ in old_model.named_parameters()]
    else:
        old_names = param_names   # mlp: actor then critic, unchanged
    if old_names != param_names:
        assert sorted(old_names) == sorted(param_names)
        old_state = new_ckpt["optim"]["state"]
        new_ckpt["optim"]["state"] = {
            new_idx: old_state[old_names.index(name)]
            for new_idx, name in enumerate(param_names)
            if old_names.index(name) in old_state
        }
    for key in ("actor.0.weight", "critic.0.weight"):
        want_in = model.state_dict()[key].shape[1]
        if state[key].shape[1] != want_in - grown:
            raise SystemExit(
                f"{key} has {state[key].shape[1]} input columns, expected "
                f"{want_in - grown}; checkpoint doesn't match the v3 layout.")
        state[key] = _splice_zero_columns(state[key], blocks)
        pstate = new_ckpt.get("optim", {}).get("state", {}).get(param_names.index(key))
        if pstate is not None:
            for moment in ("exp_avg", "exp_avg_sq"):
                if moment in pstate:
                    pstate[moment] = _splice_zero_columns(pstate[moment], blocks)
    model.load_state_dict(state)   # sanity: exact fit, no missing/extra keys
    new_ckpt["obs_dim"] = new_obs_dim
    new_ckpt["obs_schema"] = 4
    return new_ckpt


def load_agent(path: str, *, env_kind: str, obs_dim: int, n_actions: int,
               card_obs: str = "hybrid", device: str = "cpu") -> tuple[Any, dict]:
    """Load a ``train_torch.py`` checkpoint into an eval-mode model.

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
