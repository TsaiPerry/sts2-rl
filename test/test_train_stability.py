"""Tests for train_torch.py's PPO stability knobs: linear LR/entropy
annealing and the target-KL early stop.

These guard an unattended multi-day run against the two standard failure
modes — a learning rate that never leaves its warm-up value, and a single
destructive update — so what matters here is the schedule arithmetic at the
iteration boundaries and that the defaults for --env combat are untouched.
"""
from __future__ import annotations

from argparse import Namespace

import pytest

import train_torch


def parsed(monkeypatch, *argv) -> Namespace:
    monkeypatch.setattr("sys.argv", ["train_torch.py", *argv])
    return train_torch.parse_args()


# ── annealing math ───────────────────────────────────────────────────────

def test_anneal_fraction_spans_zero_to_just_under_one():
    """First iteration is 0.0 (full LR), last is (n-1)/n — never exactly 1.0,
    so the LR is still positive on the final update."""
    assert train_torch.anneal_fraction(0, 0, 10) == pytest.approx(0.0)
    assert train_torch.anneal_fraction(5, 0, 10) == pytest.approx(0.5)
    assert train_torch.anneal_fraction(9, 0, 10) == pytest.approx(0.9)


def test_anneal_fraction_restarts_from_start_iter_on_resume():
    """A run resumed at iteration 100 for 10 more iterations gets a fresh
    schedule over those 10 — not the decayed tail of the original run."""
    assert train_torch.anneal_fraction(100, 100, 10) == pytest.approx(0.0)
    assert train_torch.anneal_fraction(105, 100, 10) == pytest.approx(0.5)


def test_anneal_fraction_is_zero_when_there_are_no_iterations():
    assert train_torch.anneal_fraction(0, 0, 0) == pytest.approx(0.0)


def test_annealed_lr_decays_linearly_to_but_never_reaches_zero():
    lr = 3e-4
    at = lambda i: train_torch.anneal(lr, 0.0, train_torch.anneal_fraction(i, 0, 10))
    assert at(0) == pytest.approx(3e-4)
    assert at(5) == pytest.approx(1.5e-4)
    assert at(9) == pytest.approx(3e-5)
    assert at(9) > 0.0


def test_entropy_coef_anneals_between_its_endpoints():
    assert train_torch.anneal(0.01, 0.001, 0.0) == pytest.approx(0.01)
    assert train_torch.anneal(0.01, 0.001, 0.5) == pytest.approx(0.0055)
    # equal endpoints (the default) hold the coefficient constant
    assert train_torch.anneal(0.01, 0.01, 0.73) == pytest.approx(0.01)


# ── target-KL early stop ─────────────────────────────────────────────────

def test_kl_early_stop_uses_the_epoch_mean_not_the_last_minibatch():
    """A tail spike over an otherwise-calm epoch must not stop the loop, and
    a uniformly-hot epoch must, even when its last minibatch looks fine."""
    calm_with_tail_spike = [0.005, 0.005, 0.005, 0.09]     # mean 0.02625 > .02
    assert train_torch.kl_exceeded(calm_with_tail_spike, 0, 0.05) is False
    hot_with_calm_tail = [0.09, 0.09, 0.09, 0.005]         # mean 0.06875
    assert train_torch.kl_exceeded(hot_with_calm_tail, 0, 0.05) is True


def test_kl_early_stop_scores_only_the_current_epochs_minibatches():
    kls = [0.001, 0.001, 0.20, 0.20]      # epoch 0 calm, epoch 1 destructive
    assert train_torch.kl_exceeded(kls[:2], 0, 0.02) is False
    assert train_torch.kl_exceeded(kls, 2, 0.02) is True


def test_kl_early_stop_is_off_without_a_target():
    assert train_torch.kl_exceeded([9.9], 0, None) is False


def test_kl_early_stop_ignores_an_empty_epoch():
    assert train_torch.kl_exceeded([0.5], 1, 0.02) is False


def test_kl_early_stop_fires_mid_epoch_not_only_at_its_boundary():
    """The obs-v4 resume put a whole 8-minibatch epoch through at ~30x the
    target before the boundary check could fire, and that one epoch cost the
    policy 4 reward points permanently. Scoring the running mean after every
    minibatch has to catch it while most of the epoch is still unspent."""
    destructive = [0.13, 0.13]
    assert train_torch.kl_exceeded(destructive, 0, 0.02) is True


def test_kl_early_stop_waits_for_two_minibatches_before_it_can_fire():
    """One hot minibatch is noise, not a destructive update — the mean-not-
    last-value rationale still holds, it just no longer waits a whole epoch."""
    assert train_torch.kl_exceeded([0.13], 0, 0.02) is False
    assert train_torch.kl_exceeded([0.13], 0, 0.02, min_samples=1) is True


def test_kl_early_stop_degrades_to_the_epoch_boundary_for_one_minibatch():
    """With --minibatches 1 the caller lowers min_samples so the guard still
    has effect instead of silently never firing."""
    assert train_torch.kl_exceeded([0.13], 0, 0.02, min_samples=min(2, 1)) is True


# ── critic warm-up ───────────────────────────────────────────────────────

def test_critic_warmup_loss_leaves_the_policy_bit_identical():
    """After an env change moves the return distribution, the critic is stale
    and its advantages are mis-signed — so the warm-up trains the value head
    ALONE. Actor and critic parameters are disjoint (separate trunks, and for
    --arch entity separate encoders), so a value-only loss must leave every
    actor parameter untouched even through Adam's momentum: zero_grad(
    set_to_none=True) leaves actor grads None and Adam skips them.
    """
    import torch
    from torch import nn

    from sts2_rl.models import MaskedActorCritic

    torch.manual_seed(0)
    agent = MaskedActorCritic(obs_dim=12, n_actions=4, hidden=(16, 16))
    optimizer = torch.optim.Adam(agent.parameters(), lr=1e-3)

    obs = torch.randn(32, 12)
    mask = torch.ones(32, 4, dtype=torch.bool)
    act = torch.randint(0, 4, (32,))
    ret = torch.randn(32)

    before = {n: p.detach().clone() for n, p in agent.named_parameters()}
    # Two steps: one is enough to populate Adam's momentum, the second proves
    # that momentum doesn't leak into the actor on a later warm-up step.
    for _ in range(2):
        _, _, _, newval = agent.get_action_and_value(obs, mask, act)
        loss = 0.5 * ((newval - ret) ** 2).mean()
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(agent.parameters(), 0.5)
        optimizer.step()

    for name, param in agent.named_parameters():
        if name.startswith("actor"):
            assert torch.equal(param, before[name]), f"{name} moved during warm-up"
        else:
            assert not torch.equal(param, before[name]), f"{name} did not train"


def test_critic_warmup_is_off_by_default_and_scoped_to_this_invocation(monkeypatch):
    assert parsed(monkeypatch, "--env", "run").critic_warmup == 0
    assert parsed(monkeypatch, "--env", "run", "--critic-warmup", "20").critic_warmup == 20


# ── defaults ─────────────────────────────────────────────────────────────

def test_target_kl_defaults_on_for_run_scale_envs(monkeypatch):
    assert parsed(monkeypatch, "--env", "run").target_kl == pytest.approx(0.02)
    assert parsed(monkeypatch, "--env", "column").target_kl == pytest.approx(0.02)


def test_combat_env_defaults_are_unchanged(monkeypatch):
    """--env combat keeps the pre-existing optimization schedule: no KL stop,
    no LR anneal, constant entropy bonus."""
    args = parsed(monkeypatch, "--env", "combat")
    assert args.target_kl is None
    assert args.anneal_lr is False
    assert args.ent_coef_final == pytest.approx(args.ent_coef)


def test_target_kl_is_overridable_and_zero_turns_it_off(monkeypatch):
    assert parsed(monkeypatch, "--env", "column",
                  "--target-kl", "0.05").target_kl == pytest.approx(0.05)
    assert parsed(monkeypatch, "--env", "column", "--target-kl", "0").target_kl is None
    assert parsed(monkeypatch, "--env", "combat",
                  "--target-kl", "0.03").target_kl == pytest.approx(0.03)


def test_ent_coef_final_defaults_to_ent_coef(monkeypatch):
    args = parsed(monkeypatch, "--env", "column", "--ent-coef", "0.02")
    assert args.ent_coef_final == pytest.approx(0.02)
    args = parsed(monkeypatch, "--env", "column",
                  "--ent-coef", "0.02", "--ent-coef-final", "0.001")
    assert args.ent_coef_final == pytest.approx(0.001)


# ── end to end ───────────────────────────────────────────────────────────

def test_anneal_lr_decays_the_logged_lr_over_a_short_run(tmp_path, monkeypatch):
    """The LR must actually reach the optimizer every iteration — the flag is
    worthless if the schedule is computed and then not applied."""
    import csv

    save = str(tmp_path / "run.pt")
    monkeypatch.setattr("sys.argv", [
        "train_torch.py", "--env", "combat", "--encounter", "fuzzy_wurm_weak",
        "--timesteps", "64", "--n-envs", "2", "--n-steps", "8",
        "--minibatches", "2", "--epochs", "1", "--hidden", "16",
        "--lr", "1e-3", "--anneal-lr", "--save", save])
    train_torch.main()

    with open(train_torch.csv_path(save), newline="") as fh:
        lrs = [float(r["lr"]) for r in csv.DictReader(fh)]
    assert len(lrs) == 4
    assert lrs[0] == pytest.approx(1e-3)
    assert lrs == pytest.approx([1e-3, 7.5e-4, 5e-4, 2.5e-4])


def test_resume_with_anneal_lr_restarts_the_schedule(tmp_path, monkeypatch):
    """optimizer.load_state_dict restores the checkpoint's decayed LR; with
    --anneal-lr the second invocation must start over at --lr regardless."""
    import csv

    save = str(tmp_path / "run.pt")
    argv = ["train_torch.py", "--env", "combat", "--encounter", "fuzzy_wurm_weak",
            "--timesteps", "32", "--n-envs", "2", "--n-steps", "8",
            "--minibatches", "2", "--epochs", "1", "--hidden", "16",
            "--lr", "1e-3", "--anneal-lr", "--save", save]

    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()
    monkeypatch.setattr("sys.argv", argv)
    train_torch.main()                        # auto-resumes the same file

    with open(train_torch.csv_path(save), newline="") as fh:
        lrs = [float(r["lr"]) for r in csv.DictReader(fh)]
    assert lrs == pytest.approx([1e-3, 5e-4, 1e-3, 5e-4])
