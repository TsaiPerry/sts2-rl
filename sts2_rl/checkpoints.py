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
        raise SystemExit(
            f"checkpoint obs schema {ckpt.get('obs_schema')} != current "
            f"{obs_schema_version(spec)}; the observation layout changed — retrain.")
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
