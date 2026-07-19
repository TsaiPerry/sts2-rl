"""Tests for the raw-torch evaluation path (prompts/eval-torch.md).

Covers the policy adapter (`sts2_rl.evaluation.torch_policy` /
`load_torch_policy`) and the run-scale evaluation loop (`evaluate_run`).
Everything here runs on freshly constructed — untrained — models: the point is
that the *harness* is deterministic, dispatches on the checkpoint's arch stamp,
and refuses mismatched checkpoints, not that any particular model plays well.
"""
from __future__ import annotations

import random

import numpy as np
import pytest
import torch

from sts2_rl import STS2FullCombatEnv
from sts2_rl.checkpoints import ModelSpec, make_model
from sts2_rl.curriculum_env import STS2CurriculumRunEnv
from sts2_rl.evaluation import (
    RunEvalReport,
    evaluate_run,
    load_torch_policy,
    torch_policy,
)
from sts2_rl.models import EntityActorCritic, MaskedActorCritic
from sts2_rl.run_env import masked_random_run_policy

HIDDEN = (16,)


def save_checkpoint(path, spec: ModelSpec, obs_dim: int, n_actions: int):
    """A checkpoint in exactly train_torch.save's format, without training."""
    from sts2_rl.checkpoints import obs_schema_version

    model = make_model(spec, obs_dim, n_actions)
    torch.save(
        {
            "model": model.state_dict(),
            "optim": torch.optim.Adam(model.parameters()).state_dict(),
            "iteration": 7,
            "obs_dim": model.obs_dim,
            "n_actions": model.n_actions,
            "hidden": model.hidden,
            "arch": spec.arch,
            "obs_schema": obs_schema_version(spec),
            "env_kind": spec.env_kind,
        },
        path,
    )
    return model


def combat_env_shape(env) -> tuple[int, int]:
    return env.observation_space.shape[0], env.action_space.n


# ── Policy adapter ───────────────────────────────────────────────────────────


def test_torch_policy_is_greedy_and_deterministic():
    """Greedy = argmax over the masked logits, and repeat calls agree."""
    env = STS2FullCombatEnv()
    obs, _ = env.reset(seed=3)
    obs_dim, n_actions = combat_env_shape(env)
    model = make_model(ModelSpec("combat", hidden=HIDDEN), obs_dim, n_actions)
    model.eval()
    policy = torch_policy(model)

    mask = env.action_masks()
    action = policy(env, obs, mask)
    assert mask[action], "greedy policy picked a masked-out action"
    assert policy(env, obs, mask) == action

    expected = int(
        model.action_logits(
            torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0),
            torch.as_tensor(mask, dtype=torch.bool).unsqueeze(0),
        ).argmax(-1)
    )
    assert action == expected


def test_torch_policy_never_leaves_the_mask():
    """Every step of a whole episode picks a legal action."""
    env = STS2FullCombatEnv()
    obs, _ = env.reset(seed=1)
    obs_dim, n_actions = combat_env_shape(env)
    policy = torch_policy(make_model(ModelSpec("combat", hidden=HIDDEN), obs_dim, n_actions))

    terminated = truncated = False
    while not (terminated or truncated):
        mask = env.action_masks()
        action = policy(env, obs, mask)
        assert mask[action]
        obs, _r, terminated, truncated, _info = env.step(action)


def test_torch_policy_sample_is_seeded():
    """--sample rollouts are stochastic but reproducible from the seed."""
    env = STS2FullCombatEnv()
    obs, _ = env.reset(seed=2)
    obs_dim, n_actions = combat_env_shape(env)
    model = make_model(ModelSpec("combat", hidden=HIDDEN), obs_dim, n_actions)
    mask = env.action_masks()

    draws_a = [torch_policy(model, sample=True, seed=4)(env, obs, mask) for _ in range(1)]
    draws_b = [torch_policy(model, sample=True, seed=4)(env, obs, mask) for _ in range(1)]
    assert draws_a == draws_b
    assert all(mask[a] for a in draws_a)


@pytest.mark.parametrize("arch,cls", [("mlp", MaskedActorCritic), ("entity", EntityActorCritic)])
def test_load_dispatches_on_the_arch_stamp(tmp_path, arch, cls):
    env = STS2FullCombatEnv()
    obs_dim, n_actions = combat_env_shape(env)
    spec = ModelSpec("combat", arch=arch, hidden=HIDDEN)
    path = tmp_path / f"{arch}.pt"
    saved = save_checkpoint(path, spec, obs_dim, n_actions)

    policy, ckpt = load_torch_policy(str(path), env_kind="combat", env=env)
    assert ckpt["arch"] == arch
    assert isinstance(policy.model, cls)
    assert not policy.model.training, "loaded model must be in eval mode"

    # Same weights → same greedy choices as the in-memory model.
    obs, _ = env.reset(seed=9)
    mask = env.action_masks()
    saved.eval()
    assert policy(env, obs, mask) == torch_policy(saved)(env, obs, mask)


def test_load_refuses_env_kind_mismatch(tmp_path):
    """A combat checkpoint can't be evaluated on the run-scale env."""
    combat = STS2FullCombatEnv()
    path = tmp_path / "combat.pt"
    save_checkpoint(path, ModelSpec("combat", hidden=HIDDEN), *combat_env_shape(combat))

    run_env = STS2CurriculumRunEnv()
    with pytest.raises(SystemExit, match="env"):
        load_torch_policy(str(path), env_kind="column", env=run_env)


def test_load_refuses_schema_mismatch(tmp_path):
    env = STS2FullCombatEnv()
    obs_dim, n_actions = combat_env_shape(env)
    path = tmp_path / "stale.pt"
    save_checkpoint(path, ModelSpec("combat", hidden=HIDDEN), obs_dim, n_actions)

    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    ckpt["obs_schema"] = ckpt["obs_schema"] - 1
    torch.save(ckpt, path)

    with pytest.raises(SystemExit, match="obs schema"):
        load_torch_policy(str(path), env_kind="combat", env=env)


def test_load_does_not_mutate_the_checkpoint(tmp_path):
    env = STS2FullCombatEnv()
    path = tmp_path / "ro.pt"
    save_checkpoint(path, ModelSpec("combat", hidden=HIDDEN), *combat_env_shape(env))
    before = path.read_bytes()

    load_torch_policy(str(path), env_kind="combat", env=env)
    assert path.read_bytes() == before


def test_run_scale_checkpoint_loads_on_both_run_scale_envs(tmp_path):
    """column and run share a layout — a column checkpoint evaluates on both."""
    column = STS2CurriculumRunEnv()
    obs_dim = column.observation_space.shape[0]
    n_actions = column.action_space.n
    path = tmp_path / "column.pt"
    save_checkpoint(path, ModelSpec("column", arch="entity", hidden=HIDDEN),
                    obs_dim, n_actions)

    policy, _ = load_torch_policy(str(path), env_kind="column", env=column)
    assert isinstance(policy.model, EntityActorCritic)

    from sts2_rl.run_env import STS2RunEnv

    policy, _ = load_torch_policy(str(path), env_kind="run", env=STS2RunEnv())
    assert isinstance(policy.model, EntityActorCritic)


# ── Run-scale evaluation ─────────────────────────────────────────────────────


def test_evaluate_run_smoke_on_an_untrained_model(tmp_path):
    """A fresh model over a short seeded column batch produces a coherent
    report: every field is populated and the aggregates agree with the
    per-episode lists."""
    env = STS2CurriculumRunEnv(column_rooms=3)
    obs_dim, n_actions = env.observation_space.shape[0], env.action_space.n
    path = tmp_path / "fresh.pt"
    save_checkpoint(path, ModelSpec("column", hidden=HIDDEN), obs_dim, n_actions)
    policy, _ = load_torch_policy(str(path), env_kind="column", env=env)

    report = evaluate_run(policy, episodes=3, seed=0, env=env)

    assert isinstance(report, RunEvalReport)
    assert report.episodes == 3
    assert len(report.floors) == len(report.acts) == len(report.decisions) == 3
    assert 0 <= report.wins <= 3
    assert report.win_rate == report.wins / 3
    assert report.mean_floor == pytest.approx(float(np.mean(report.floors)))
    assert report.median_floor == pytest.approx(float(np.median(report.floors)))
    assert all(f >= 0 for f in report.floors)
    assert all(d > 0 for d in report.decisions)
    # Wins and deaths partition the episodes.
    assert len(report.win_hp) + len(report.death_floors) == 3 - report.truncated
    assert sum(report.act_histogram.values()) == 3


def test_evaluate_run_is_deterministic_under_a_seed(tmp_path):
    """Same seed → same episodes → same report (the harness contract)."""
    obs_dim = n_actions = None

    def one_report():
        env = STS2CurriculumRunEnv(column_rooms=3)
        nonlocal obs_dim, n_actions
        obs_dim = env.observation_space.shape[0]
        n_actions = env.action_space.n
        policy, _ = load_torch_policy(str(path), env_kind="column", env=env)
        return evaluate_run(policy, episodes=2, seed=11, env=env)

    env = STS2CurriculumRunEnv(column_rooms=3)
    path = tmp_path / "det.pt"
    save_checkpoint(path, ModelSpec("column", hidden=HIDDEN),
                    env.observation_space.shape[0], env.action_space.n)

    assert one_report() == one_report()


def test_evaluate_run_baseline_row():
    """The masked-random baseline runs through the same loop."""
    env = STS2CurriculumRunEnv(column_rooms=3)
    report = evaluate_run(
        masked_random_run_policy(random.Random(0)), episodes=2, seed=5, env=env)
    assert report.episodes == 2
    assert len(report.floors) == 2
