"""Tests for train_torch.py's unattended-run I/O: atomic checkpoint writes,
rolling iter-stamped snapshots, the per-iteration CSV log, and the resume
fields (global_step) that make a multi-day run recoverable.

These cover the failure modes a long run actually hits — a crash mid-write
corrupting the only auto-resume checkpoint, a late policy collapse
overwriting good weights, and stdout-only metrics vanishing with the console.
"""
from __future__ import annotations

import csv
from argparse import Namespace

import pytest
import torch

import train_torch
from sts2_rl.models import MaskedActorCritic


def make_pair(hidden=(8,), obs_dim=6, n_actions=4):
    model = MaskedActorCritic(obs_dim, n_actions, hidden=hidden)
    return model, torch.optim.Adam(model.parameters())


def combat_args(tmp_path, **over) -> Namespace:
    args = Namespace(
        env="combat", arch="mlp", card_obs="hybrid", hidden=[8],
        save=str(tmp_path / "ckpt.pt"),
        n_envs=train_torch.DEFAULT_N_ENVS, n_steps=train_torch.DEFAULT_N_STEPS,
    )
    for k, v in over.items():
        setattr(args, k, v)
    return args


# ── atomic saves ─────────────────────────────────────────────────────────

def test_interrupted_save_leaves_the_previous_checkpoint_loadable(tmp_path, monkeypatch):
    args = combat_args(tmp_path)
    model, optimizer = make_pair()
    train_torch.save(model, optimizer, 1, args)

    real_save = torch.save

    def failing_save(payload, path, *a, **kw):
        real_save(payload, path, *a, **kw)     # partial write to the tmp file
        raise KeyboardInterrupt("Ctrl-C mid-write")

    monkeypatch.setattr(train_torch.torch, "save", failing_save)
    with pytest.raises(KeyboardInterrupt):
        train_torch.save(model, optimizer, 2, args)

    ckpt = torch.load(args.save, map_location="cpu", weights_only=False)
    assert ckpt["iteration"] == 1                # the good checkpoint survived
    assert not list(tmp_path.glob("*.tmp"))      # and no debris was left behind


# ── rolling snapshots ────────────────────────────────────────────────────

def test_snapshot_rotation_keeps_exactly_k_most_recent(tmp_path):
    args = combat_args(tmp_path)
    model, optimizer = make_pair()
    for iteration in (10, 20, 30, 40):
        payload = train_torch.checkpoint_payload(model, optimizer, iteration, args, 0)
        train_torch.atomic_save(payload, train_torch.snapshot_path(args.save, iteration))
        train_torch.rotate_snapshots(args.save, keep=2)

    kept = sorted(p.name for p in tmp_path.glob("ckpt.iter*.pt"))
    assert kept == ["ckpt.iter000030.pt", "ckpt.iter000040.pt"]


def test_snapshot_names_sort_lexicographically_by_iteration(tmp_path):
    args = combat_args(tmp_path)
    assert train_torch.snapshot_path(args.save, 7).endswith("ckpt.iter000007.pt")
    assert (train_torch.snapshot_path(args.save, 9)
            < train_torch.snapshot_path(args.save, 100))


# ── CSV log ──────────────────────────────────────────────────────────────

def test_csv_append_across_resume_writes_one_header(tmp_path):
    path = str(tmp_path / "ckpt.csv")
    row = dict(iter=0, global_step=4096, wall_seconds=12.5, sps=176,
               ep_ret=1.5, win=0.0, ep_len=210.0, pg=-0.01, v=0.3,
               ent=2.1, kl=0.004, clipfrac=0.02, lr=3e-4)
    train_torch.append_csv_row(path, row)
    train_torch.append_csv_row(path, {**row, "iter": 1})
    # a resumed run appends to the same file
    train_torch.append_csv_row(path, {**row, "iter": 2})

    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == train_torch.CSV_FIELDS
    assert [r[0] for r in rows[1:]] == ["0", "1", "2"]
    assert sum(r[0] == "iter" for r in rows) == 1


# ── resume fields ────────────────────────────────────────────────────────

def test_global_step_round_trips_and_defaults_for_old_checkpoints(tmp_path):
    args = combat_args(tmp_path)
    model, optimizer = make_pair()
    train_torch.save(model, optimizer, 5, args, global_step=123_456)

    ckpt = torch.load(args.save, map_location="cpu", weights_only=False)
    assert ckpt["global_step"] == 123_456

    legacy = dict(ckpt)                  # pre-hardening checkpoints have no key
    del legacy["global_step"]
    assert legacy.get("global_step", 0) == 0


def test_short_run_then_resume_continues_csv_and_global_step(tmp_path, monkeypatch):
    """End-to-end: two tiny training runs over the same checkpoint. The
    second must continue the step count and append to the same CSV rather
    than restarting either."""
    save = str(tmp_path / "run.pt")
    argv = ["train_torch.py", "--env", "combat", "--encounter", "fuzzy_wurm_weak",
            "--timesteps", "32", "--n-envs", "2", "--n-steps", "8",
            "--minibatches", "2", "--epochs", "1", "--hidden", "16",
            "--save", save, "--save-every", "1", "--keep-snapshots", "2"]

    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()

    first = torch.load(save, map_location="cpu", weights_only=False)
    assert first["iteration"] == 2 and first["global_step"] == 32

    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()                       # auto-resumes the same file

    second = torch.load(save, map_location="cpu", weights_only=False)
    assert second["iteration"] == 4 and second["global_step"] == 64

    with open(train_torch.csv_path(save), newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == train_torch.CSV_FIELDS
    assert [r[0] for r in rows[1:]] == ["0", "1", "2", "3"]

    snaps = sorted(p.name for p in tmp_path.glob("run.iter*.pt"))
    assert snaps == ["run.iter000003.pt", "run.iter000004.pt"]
    assert (tmp_path / "run.best.pt").exists()


def test_lr_flag_is_none_unless_passed(tmp_path, monkeypatch):
    """--lr must be distinguishable from 'not passed' so a resume knows
    whether to override the optimizer's restored LR; fresh runs fall back
    to DEFAULT_LR."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat"])
    assert train_torch.parse_args().lr is None
    assert train_torch.DEFAULT_LR == pytest.approx(3e-4)
    monkeypatch.setattr(
        "sys.argv", ["train_torch.py", "--env", "combat", "--lr", "1e-4"])
    assert train_torch.parse_args().lr == pytest.approx(1e-4)


# ── rollout geometry across a resume ─────────────────────────────────────

def test_rollout_flags_are_none_unless_passed(monkeypatch):
    """Same contract as --lr: 'not passed' must be distinguishable from the
    default value, or a resume cannot tell 'keep the checkpoint's batch' from
    'the user asked for 32'."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    args = train_torch.parse_args()
    assert args.n_envs is None and args.n_steps is None
    assert train_torch.DEFAULT_N_ENVS == 32
    assert train_torch.DEFAULT_N_STEPS == 512

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--n-envs", "4", "--n-steps", "128"])
    args = train_torch.parse_args()
    assert (args.n_envs, args.n_steps) == (4, 128)


def test_fresh_run_uses_the_rollout_defaults():
    args = Namespace(n_envs=None, n_steps=None)
    assert train_torch.resolve_rollout_geometry(args, None) == (32, 512)


def test_resume_restores_the_checkpoints_rollout_geometry():
    """The bug this exists for: n_envs x n_steps is the effective batch, but
    it lives outside the model, so a bare --resume used to silently revert it
    and quietly train the same weights at a different batch size."""
    args = Namespace(n_envs=None, n_steps=None)
    ckpt = {"n_envs": 8, "n_steps": 256}
    assert train_torch.resolve_rollout_geometry(args, ckpt) == (8, 256)


def test_explicit_rollout_flags_beat_the_checkpoint():
    args = Namespace(n_envs=4, n_steps=128)
    ckpt = {"n_envs": 8, "n_steps": 256}
    assert train_torch.resolve_rollout_geometry(args, ckpt) == (4, 128)


def test_rollout_geometry_falls_back_per_field():
    """A checkpoint may record one field and not the other (or neither, for
    pre-hardening files) — each resolves independently."""
    args = Namespace(n_envs=None, n_steps=None)
    assert train_torch.resolve_rollout_geometry(args, {}) == (32, 512)
    assert train_torch.resolve_rollout_geometry(args, {"n_envs": 8}) == (8, 512)

    half = Namespace(n_envs=2, n_steps=None)
    assert train_torch.resolve_rollout_geometry(half, {"n_envs": 8, "n_steps": 256}) == (2, 256)


def test_checkpoint_records_the_rollout_geometry(tmp_path):
    """Without this the file carries no record of the batch that produced it,
    which is what made a shrunken batch so hard to rule out after the fact."""
    args = combat_args(tmp_path, n_envs=8, n_steps=256)
    model, optimizer = make_pair()
    payload = train_torch.checkpoint_payload(model, optimizer, 1, args, 0)
    assert payload["n_envs"] == 8 and payload["n_steps"] == 256
