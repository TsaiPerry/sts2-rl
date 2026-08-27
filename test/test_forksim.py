"""test/test_forksim.py — deterministic fork-by-replay (Phase 3)."""
import os

import numpy as np
import pytest

from sts2_rl.forksim import CombatFork
from sts2_rl.snapshots import load_snapshots

BANK = "runs/snapshots/foresight_dev.jsonl"   # built in step 2

#: the dev bank is a local build artifact (gitignored), so a fresh clone has
#: no way to run these; skip rather than fail.
pytestmark = pytest.mark.skipif(
    not os.path.exists(BANK), reason="dev bank is local-only (gitignored)")


def _fork():
    snap = load_snapshots(BANK)[0]
    return CombatFork(snap, seed=123, env_kwargs={"ascension": 10})


def test_replay_is_deterministic():
    f = _fork()
    e1 = f.replay([0]); e2 = f.replay([0])
    o1, o2 = e1._build_obs(), e2._build_obs()
    np.testing.assert_array_equal(o1["f"], o2["f"])
    np.testing.assert_array_equal(o1["i"], o2["i"])


def test_same_salt_same_branch_different_salt_differs():
    f = _fork()
    # end-turn (action 0) redraws a hand -> pile rng is consumed.
    #
    # Deviation from the brief's literal `branch([], 0, ...)`: on THIS
    # snapshot (the 10-card starter deck, 5 in hand / 5 in draw) the FIRST
    # end-turn draws the draw pile's last 5 cards and never RESHUFFLES, so
    # the salt cannot reach the hand (the step still makes a draw or two —
    # it just makes none the reseed can change) and every salt gives the
    # identical hand — the
    # brief's "always redraws" premise is false for turn 1. One end-turn of
    # prefix empties the pile, so the branch step's draw MUST reshuffle; that
    # is the rng consumption the test is about. Verified: with the prefix,
    # salts 1/2/3 give three different hands.
    e1, _, _ = f.branch([0], 0, salt=1)
    e2, _, _ = f.branch([0], 0, salt=1)
    e3, _, _ = f.branch([0], 0, salt=2)
    a, b, c = (e._build_obs()["i"] for e in (e1, e2, e3))
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)
