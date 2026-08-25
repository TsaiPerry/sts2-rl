"""Tests for train_torch.py's unattended-run I/O: atomic checkpoint writes,
rolling iter-stamped snapshots, the per-iteration CSV log, and the resume
fields (global_step) that make a multi-day run recoverable.

These cover the failure modes a long run actually hits — a crash mid-write
corrupting the only auto-resume checkpoint, a late policy collapse
overwriting good weights, and stdout-only metrics vanishing with the console.
"""
from __future__ import annotations

import csv
import os
from argparse import Namespace

import pytest
import torch

import train_torch
from sts2_rl.models import MaskedActorCritic
from sts2_rl.vec_env import build_env


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


# ── finish-time snapshot cleanup ─────────────────────────────────────────
#
# Snapshots exist to survive a *late* collapse mid-run; once the run has
# finished cleanly they are dead weight (they dominated a 4.4 GB runs/ dir).
# The final --save checkpoint and .best.pt are NOT touched: the curriculum
# scripts chain stages through `--resume runs/..._sNN.pt`, so deleting the
# final file would break the handoff.

def _lay_down_run(tmp_path, args, iterations=(10, 20, 30)):
    """Write one finished run's files: final, best and iter snapshots."""
    model, optimizer = make_pair()
    payload = train_torch.checkpoint_payload(model, optimizer, 30, args, 0)
    train_torch.atomic_save(payload, args.save)
    train_torch.atomic_save(payload, train_torch.best_path(args.save))
    for iteration in iterations:
        train_torch.atomic_save(
            payload, train_torch.snapshot_path(args.save, iteration))


def test_cleanup_deletes_snapshots_but_keeps_final_and_best(tmp_path):
    args = combat_args(tmp_path)
    _lay_down_run(tmp_path, args)

    train_torch.cleanup_snapshots(args.save)

    assert not list(tmp_path.glob("ckpt.iter*.pt"))       # snapshots gone
    assert (tmp_path / "ckpt.pt").exists()                # stage handoff intact
    assert (tmp_path / "ckpt.best.pt").exists()


def test_cleanup_leaves_another_runs_snapshots_alone(tmp_path):
    """The stem is per-run: sibling runs share runs/ and must not be hit."""
    args = combat_args(tmp_path)
    other = combat_args(tmp_path, save=str(tmp_path / "other.pt"))
    _lay_down_run(tmp_path, args)
    _lay_down_run(tmp_path, other)

    train_torch.cleanup_snapshots(args.save)

    assert not list(tmp_path.glob("ckpt.iter*.pt"))
    assert len(list(tmp_path.glob("other.iter*.pt"))) == 3


def test_cleanup_is_a_noop_when_there_are_no_snapshots(tmp_path):
    args = combat_args(tmp_path)
    model, optimizer = make_pair()
    train_torch.save(model, optimizer, 1, args)

    train_torch.cleanup_snapshots(args.save)          # must not raise

    assert (tmp_path / "ckpt.pt").exists()


def test_cleanup_returns_the_number_of_files_removed(tmp_path):
    args = combat_args(tmp_path)
    _lay_down_run(tmp_path, args, iterations=(10, 20, 30, 40))
    assert train_torch.cleanup_snapshots(args.save) == 4
    assert train_torch.cleanup_snapshots(args.save) == 0


def _short_run_argv(save, *extra):
    return ["train_torch.py", "--env", "combat", "--arch", "entset",
            "--encounter", "fuzzy_wurm_weak",
            "--timesteps", "192", "--n-envs", "2", "--n-steps", "48",
            "--minibatches", "2", "--epochs", "1", "--hidden", "16",
            "--save", save, "--save-every", "1", "--keep-snapshots", "5",
            *extra]


def test_finished_run_cleans_up_its_own_snapshots(tmp_path, monkeypatch):
    """End to end: the default finish path leaves the run resumable, no debris."""
    save = str(tmp_path / "run.pt")
    monkeypatch.setattr("sys.argv", _short_run_argv(save))
    train_torch.main()

    assert not list(tmp_path.glob("run.iter*.pt"))
    assert (tmp_path / "run.pt").exists()      # next curriculum stage can --resume


def test_interrupted_run_keeps_every_snapshot(tmp_path, monkeypatch):
    """The user-facing contract: Ctrl-C mid-run must not cost you a rollback
    point. The interrupt raises past the cleanup call, which lives on the
    normal completion path only."""
    save = str(tmp_path / "run.pt")
    real_save = train_torch.atomic_save
    n_calls = 0

    def interrupt_on_second_snapshot(payload, path, *a, **kw):
        nonlocal n_calls
        real_save(payload, path, *a, **kw)
        if ".iter" in path:
            n_calls += 1
            if n_calls == 2:
                raise KeyboardInterrupt("Ctrl-C mid-run")

    monkeypatch.setattr(train_torch, "atomic_save", interrupt_on_second_snapshot)
    monkeypatch.setattr("sys.argv", _short_run_argv(save))
    with pytest.raises(KeyboardInterrupt):
        train_torch.main()

    assert len(list(tmp_path.glob("run.iter*.pt"))) == 2   # both survived


def test_no_cleanup_snapshots_flag_keeps_them_on_a_clean_finish(tmp_path, monkeypatch):
    save = str(tmp_path / "run.pt")
    monkeypatch.setattr("sys.argv", _short_run_argv(save, "--no-cleanup-snapshots"))
    train_torch.main()

    assert len(list(tmp_path.glob("run.iter*.pt"))) == 2


# ── CSV log ──────────────────────────────────────────────────────────────

def test_csv_path_lands_in_a_run_logs_subdir(tmp_path):
    """The per-iteration logs live in runs/run_logs/, not beside the .pt —
    they are bulky and regenerable, so that directory is gitignored."""
    args = combat_args(tmp_path)
    assert train_torch.csv_path(args.save) == str(
        tmp_path / train_torch.RUN_LOGS_DIR / "ckpt.csv")


def test_csv_path_handles_a_bare_relative_save_path(tmp_path):
    assert train_torch.csv_path("ckpt.pt") == os.path.join(
        train_torch.RUN_LOGS_DIR, "ckpt.csv")


def test_a_real_run_writes_its_csv_into_run_logs(tmp_path, monkeypatch):
    """End to end: the directory is created on demand, no pre-made tree."""
    save = str(tmp_path / "run.pt")
    monkeypatch.setattr("sys.argv", _short_run_argv(save))
    train_torch.main()

    assert (tmp_path / train_torch.RUN_LOGS_DIR / "run.csv").exists()
    assert not (tmp_path / "run.csv").exists()

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
    than restarting either.

    ``n_steps`` is 48, not some smaller "just enough to log two iterations"
    number, on purpose: ``run.best.pt`` is only written once a completed
    episode gives ``best_metric`` (win-rate, for --env combat) a real,
    non-NaN score, so this test's ability to exercise that path depends on
    at least one ``fuzzy_wurm_weak`` episode finishing inside the rollout.
    Under a random-ish masked policy that fight resolves in ~10-27 steps
    (measured directly against the env), so 48 steps/env per iteration is
    comfortable headroom, not a tight fit. A smaller budget (this test used
    to run only 8 steps/env per iteration) makes episode completion a coin
    flip driven by whatever the model's random weight init happens to do to
    torch's global RNG stream -- which is exactly what broke this test when
    an unrelated observation-schema widening shifted that stream's
    consumption at init time: same seeds, same code path, zero episodes
    completed in the whole run, so ``run.best.pt`` was never created. The
    fix is to make completion a near-certainty instead of pinning the old
    lucky trajectory or loosening the assertion into a vacuous one
    (mutation-checked by temporarily breaking resume in a scratch script and
    confirming this test goes red)."""
    save = str(tmp_path / "run.pt")
    # --arch mlp/entity are refused against the real (v4-schema) combat env,
    # so --arch entset (now also the CLI default) is passed explicitly here
    # to keep this test working regardless of what the default is.
    argv = ["train_torch.py", "--env", "combat", "--arch", "entset",
            "--encounter", "fuzzy_wurm_weak",
            "--timesteps", "192", "--n-envs", "2", "--n-steps", "48",
            "--minibatches", "2", "--epochs", "1", "--hidden", "16",
            "--save", save, "--save-every", "1", "--keep-snapshots", "2",
            # This test asserts snapshot *rotation* survives a resume; finish-time
            # cleanup (on by default) would wipe them at the end of both runs and
            # make that assertion vacuous. Cleanup has its own tests above.
            "--no-cleanup-snapshots"]

    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()

    first = torch.load(save, map_location="cpu", weights_only=False)
    assert first["iteration"] == 2 and first["global_step"] == 192

    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()                       # auto-resumes the same file

    second = torch.load(save, map_location="cpu", weights_only=False)
    assert second["iteration"] == 4 and second["global_step"] == 384

    with open(train_torch.csv_path(save), newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == train_torch.CSV_FIELDS
    assert [r[0] for r in rows[1:]] == ["0", "1", "2", "3"]

    snaps = sorted(p.name for p in tmp_path.glob("run.iter*.pt"))
    assert snaps == ["run.iter000003.pt", "run.iter000004.pt"]
    assert (tmp_path / "run.best.pt").exists(), (
        "no completed episode produced a scoreable win-rate across either "
        "run -- either fuzzy_wurm_weak got harder/longer, or resume is "
        "broken and the second run isn't really continuing the rollout")


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


# ── branch annealing ─────────────────────────────────────────────────────

def test_branch_prob_flag_reaches_the_env_spec(monkeypatch):
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "column"])
    args = train_torch.parse_args()
    assert args.branch_prob == 0.0
    assert train_torch.env_spec(args).branch_prob == 0.0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "column",
                                     "--branch-prob", "0.25"])
    assert train_torch.env_spec(train_torch.parse_args()).branch_prob == 0.25


def test_branch_prob_is_rejected_outside_the_column_env(monkeypatch):
    """On --env run every map already branches, so a non-zero --branch-prob
    there is a misunderstanding of the knob, not a no-op worth honouring."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--branch-prob", "0.5"])
    with pytest.raises(SystemExit, match="branch-prob"):
        train_torch.parse_args()


# ── ascension flag ────────────────────────────────────────────────────────

def test_ascension_flag_reaches_the_env_spec(monkeypatch):
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    args = train_torch.parse_args()
    assert args.ascension == 0
    assert train_torch.env_spec(args).ascension == 0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--ascension", "10"])
    assert train_torch.env_spec(train_torch.parse_args()).ascension == 10


def test_ascension_is_accepted_on_the_combat_env(monkeypatch):
    """v8 plan Task 5: relaxed -- STS2FullCombatEnv takes ascension (v7 Task
    10 wired it into CombatState/hooks; eval.py's guard was relaxed there
    too). The v8 curriculum trains combat stages at asc 10 directly, so
    --env combat --ascension must no longer raise."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--ascension", "5"])
    args = train_torch.parse_args()
    assert args.ascension == 5
    assert train_torch.env_spec(args).ascension == 5


def test_hp_and_potion_potential_scale_rejected_on_the_combat_env(monkeypatch):
    """Unlike --ascension, the v8 HP/potion shaping knobs are run/column-only
    -- STS2FullCombatEnv doesn't take either kwarg."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--hp-potential-scale", "1.0"])
    with pytest.raises(SystemExit, match="hp-potential-scale"):
        train_torch.parse_args()

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--potion-potential-scale", "1.0"])
    with pytest.raises(SystemExit, match="potion-potential-scale"):
        train_torch.parse_args()


def test_hp_and_potion_potential_scale_flags_reach_the_env_spec(monkeypatch):
    """v8 plan Task 5: --hp-potential-scale/--potion-potential-scale default
    off (bit-identical env) and thread through env_spec() like the other
    v7/v8 reward flags."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    args = train_torch.parse_args()
    assert args.hp_potential_scale == 0.0
    assert args.potion_potential_scale == 0.0
    spec = train_torch.env_spec(args)
    assert spec.hp_potential_scale == 0.0
    assert spec.potion_potential_scale == 0.0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "column",
                                     "--hp-potential-scale", "4.0",
                                     "--potion-potential-scale", "0.3"])
    spec = train_torch.env_spec(train_torch.parse_args())
    assert spec.hp_potential_scale == 4.0
    assert spec.potion_potential_scale == 0.3


def test_potion_death_penalty_flag_threads_and_is_run_only(monkeypatch):
    """v15.1: --potion-death-penalty defaults off, reaches the EnvSpec, and
    is rejected on the combat env like the other run-scale reward knobs."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    args = train_torch.parse_args()
    assert args.potion_death_penalty == 0.0
    assert train_torch.env_spec(args).potion_death_penalty == 0.0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--potion-death-penalty", "0.3"])
    spec = train_torch.env_spec(train_torch.parse_args())
    assert spec.potion_death_penalty == 0.3

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--potion-death-penalty", "0.3"])
    with pytest.raises(SystemExit, match="potion-death-penalty"):
        train_torch.parse_args()


def test_energy_waste_penalty_flag_threads_and_is_run_only(monkeypatch):
    """v16: --energy-waste-penalty defaults off, reaches the EnvSpec and
    the env, and is rejected on the combat env like the other run-scale
    reward knobs."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    args = train_torch.parse_args()
    assert args.energy_waste_penalty == 0.0
    assert train_torch.env_spec(args).energy_waste_penalty == 0.0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--energy-waste-penalty", "0.02"])
    spec = train_torch.env_spec(train_torch.parse_args())
    assert spec.energy_waste_penalty == 0.02
    env = build_env(spec)
    assert env._energy_waste_penalty == 0.02

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--energy-waste-penalty", "0.02"])
    with pytest.raises(SystemExit, match="energy-waste-penalty"):
        train_torch.parse_args()


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


def test_potion_ent_coef_flag_parses_and_is_guarded(monkeypatch):
    """v16: --potion-ent-coef defaults off, parses, and is rejected off
    the entset/run pair (the potion index ranges are run-scale entset
    layout constants)."""
    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run"])
    assert train_torch.parse_args().potion_ent_coef == 0.0

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--potion-ent-coef", "0.01"])
    assert train_torch.parse_args().potion_ent_coef == 0.01

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "combat",
                                     "--potion-ent-coef", "0.01"])
    with pytest.raises(SystemExit, match="potion-ent-coef"):
        train_torch.parse_args()

    monkeypatch.setattr("sys.argv", ["train_torch.py", "--env", "run",
                                     "--arch", "entity",
                                     "--potion-ent-coef", "0.01"])
    with pytest.raises(SystemExit, match="potion-ent-coef"):
        train_torch.parse_args()
