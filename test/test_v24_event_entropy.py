"""v24: event-step entropy bonus. Event steps are found via the
run-obs `event.present` float (the action mask CANNOT distinguish
events — CHOICE_BASE..+16 is shared by map/shop/rest/reward), and the
bonus is the entropy of the renormalized legal-choice distribution.
The potion-ent precedent bought nothing measurable (v16) — this term is
pre-registered skeptically in the run log; the code contract here is
just: right steps, right slice, right renormalization."""
import torch
from sts2_rl.run_env import CHOICE_BASE, CHOICE_SLOTS
from train_torch import event_entropy_bonus

N_ACT = 260  # >= CHOICE_BASE + CHOICE_SLOTS; use the real n_actions const


def _uniform_probs(mask):
    p = mask.float()
    return p / p.sum(-1, keepdim=True)


def test_event_step_uniform_choices_gives_log_k():
    mask = torch.zeros(1, N_ACT, dtype=torch.bool)
    mask[0, CHOICE_BASE:CHOICE_BASE + 4] = True
    f = torch.zeros(1, 8); f[0, 3] = 1.0   # event.present at col 3
    ent = event_entropy_bonus(_uniform_probs(mask), mask, f, 3)
    assert torch.isclose(ent, torch.log(torch.tensor(4.0)))


def test_collapsed_event_gives_zero():
    mask = torch.zeros(1, N_ACT, dtype=torch.bool)
    mask[0, CHOICE_BASE:CHOICE_BASE + 4] = True
    probs = torch.zeros(1, N_ACT); probs[0, CHOICE_BASE] = 1.0
    f = torch.zeros(1, 8); f[0, 3] = 1.0
    ent = event_entropy_bonus(probs, mask, f, 3)
    assert ent.item() < 1e-6


def test_non_event_steps_excluded():
    mask = torch.zeros(2, N_ACT, dtype=torch.bool)
    mask[:, CHOICE_BASE:CHOICE_BASE + 4] = True
    probs = _uniform_probs(mask)
    f = torch.zeros(2, 8)                  # no event.present anywhere
    ent = event_entropy_bonus(probs, mask, f, 3)
    assert ent.item() == 0.0


def test_single_option_event_excluded():
    mask = torch.zeros(1, N_ACT, dtype=torch.bool)
    mask[0, CHOICE_BASE] = True            # 1 legal choice: no entropy to have
    probs = torch.zeros(1, N_ACT); probs[0, CHOICE_BASE] = 1.0
    f = torch.zeros(1, 8); f[0, 3] = 1.0
    assert event_entropy_bonus(probs, mask, f, 3).item() == 0.0
