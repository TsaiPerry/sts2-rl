"""Tests for the lethal-arithmetic probe suite (OBS_PLAN Phase 4, step 11).

The probes only measure anything if they are deterministic, solvable, and
discriminating — so: every build is byte-identical, the numerate oracle aces
the suite, and naive policies (never act / always attack / illegal actions)
fail exactly the probes their blind spot predicts.

Run with:  py -m pytest test/test_probes.py -v
"""
from __future__ import annotations

import pytest

from sts2_rl.evaluation import (
    evaluate_probes,
    evaluate_win_rate,
    masked_random_policy,
)
from sts2_rl.full_env import MAX_ENEMIES
from sts2_rl.probes import PROBES, PROBE_PLAYER_HP, lethal_oracle


@pytest.mark.parametrize("probe", PROBES, ids=lambda p: p.id)
def test_probe_is_well_formed(probe):
    env = probe.build()
    s = env._state
    assert sorted(c.id for c in s.player.hand) == ["defend", "strike"]
    assert s.player.energy == 1                # exactly one meaningful play
    assert s.player.hp == PROBE_PLAYER_HP
    mask = env.action_masks()
    assert mask[0]                             # can always end the turn
    assert mask[1:].any()                      # and there is a real choice


@pytest.mark.parametrize("probe", PROBES, ids=lambda p: p.id)
def test_probe_builds_are_deterministic(probe):
    """``_build_obs()`` returns the v4 ``{"f": ndarray, "i": ndarray}`` dict
    (OBS_SCHEMA.md Sec.2), not a flat array — hash both halves independently
    so a divergence confined to just the int half (e.g. a vocab id) can't
    hide behind an unchanged float half, or vice versa."""
    a, b = probe.build()._build_obs(), probe.build()._build_obs()
    assert a["f"].tobytes() == b["f"].tobytes()
    assert a["i"].tobytes() == b["i"].tobytes()


def test_oracle_aces_the_suite():
    accuracy, results = evaluate_probes(lethal_oracle)
    assert accuracy == 1.0, [r.probe_id for r in results if not r.passed]


def test_end_turn_policy_fails_every_probe():
    # Never acting dies to every telegraphed 12 and takes no kill.
    accuracy, _ = evaluate_probes(lambda env, obs, mask: 0)
    assert accuracy == 0.0


# Attack-only play passes exactly the probes where striking is the answer and
# fails every block-or-die probe — the suite separates the two failure modes.
_STRIKE_IS_RIGHT = {
    "lethal_edge_kill",
    "incoming_survivable_race",
    "vulnerable_makes_lethal",
    "kill_without_weak",
}


def _attack_spam(env, obs, mask):
    s = env.unwrapped._state
    for h, card in enumerate(s.player.hand):
        action = 1 + h * MAX_ENEMIES           # enemy 0 — the only probe enemy
        if card.base_damage is not None and mask[action]:
            return action
    return 0


def test_attack_spam_passes_kills_and_fails_holds():
    _, results = evaluate_probes(_attack_spam)
    for r in results:
        assert r.passed == (r.probe_id in _STRIKE_IS_RIGHT), (r.probe_id, r.passed)


def test_illegal_actions_fail_the_probe():
    # A potion action with no potions carried is never legal.
    accuracy, results = evaluate_probes(lambda env, obs, mask: env.n_actions - 1)
    assert accuracy == 0.0
    assert all(r.actions == () for r in results)


def test_evaluate_win_rate_runs():
    from sts2_rl import FUZZY_WURM_ENCOUNTER, STS2FullCombatEnv

    report = evaluate_win_rate(
        masked_random_policy(0),
        episodes=2,
        seed=0,
        env=STS2FullCombatEnv(encounter=FUZZY_WURM_ENCOUNTER, max_steps=300),
    )
    assert report.episodes == 2
    assert 0.0 <= report.win_rate <= 1.0
    assert report.mean_turns > 0
