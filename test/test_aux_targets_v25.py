"""test/test_aux_targets_v25.py — v25 foresight aux targets (plan
2026-08-26-foresight-v25-v26, Tasks 1-2). Hand-built columns, single env
axis unless the test says otherwise."""
from __future__ import annotations

import numpy as np

from sts2_rl.aux_targets import hp_lost_next_turn, win_outcome


def col(vals):
    """(N,) list -> (N, 1) float32 column."""
    return np.asarray(vals, dtype=np.float32).reshape(-1, 1)


T = 1.0 / 30.0   # one combat turn in the obs encoding


def test_next_turn_window_captures_enemy_phase_loss():
    # turn 7 for two decisions, then turn 8: the 11-dmg bite + 3 burn land
    # between the last turn-7 step and the first turn-8 step.
    turn = col([7 * T, 7 * T, 8 * T, 8 * T])
    hp   = col([0.19, 0.19, 0.05, 0.05])
    done = col([1, 0, 0, 0])
    t, v = hp_lost_next_turn(turn, hp, done)
    assert v[0, 0] and v[1, 0]
    np.testing.assert_allclose(t[0, 0], 0.14, atol=1e-6)
    np.testing.assert_allclose(t[1, 0], 0.14, atol=1e-6)


def test_combat_end_transition_is_not_a_loss():
    # Victory: combat block zeroes out (hp_ratio 0.30 -> 0.0). The guarded
    # diff must NOT read that as losing 30% HP.
    turn = col([5 * T, 5 * T, 0.0, 0.0])
    hp   = col([0.30, 0.30, 0.0, 0.0])
    done = col([1, 0, 0, 0])
    t, v = hp_lost_next_turn(turn, hp, done)
    assert v[0, 0]
    np.testing.assert_allclose(t[0, 0], 0.0, atol=1e-6)


def test_out_of_combat_steps_invalid():
    turn = col([0.0, 0.0, 3 * T])
    hp   = col([0.0, 0.0, 0.5])
    done = col([1, 0, 0])
    _, v = hp_lost_next_turn(turn, hp, done)
    assert not v[0, 0] and not v[1, 0]


def test_death_before_boundary_is_valid_and_counts_drops():
    # Turn never advances: the player dies mid-window; done at index 3
    # fences the segment. Drops inside the segment count; valid=True
    # (closed-segment branch, same as hp_lost_next_floors).
    turn = col([4 * T, 4 * T, 4 * T, 2 * T])
    hp   = col([0.20, 0.10, 0.04, 0.90])
    done = col([1, 0, 0, 1])
    t, v = hp_lost_next_turn(turn, hp, done)
    assert v[0, 0]
    np.testing.assert_allclose(t[0, 0], 0.16, atol=1e-6)


def test_open_window_at_buffer_end_invalid():
    turn = col([6 * T, 6 * T])
    hp   = col([0.5, 0.5])
    done = col([1, 0])
    _, v = hp_lost_next_turn(turn, hp, done)
    assert not v[1, 0]


def test_no_window_crosses_done():
    # Episode 2 starts at index 2 with a different turn value; ep 1's
    # window must not treat it as ep 1's boundary. Ep 1's segment is open
    # at its end (no boundary before the fence closes it via done at 2 --
    # done INSIDE the window closes the segment -> valid, drops to seg end).
    turn = col([9 * T, 9 * T, 1 * T, 1 * T])
    hp   = col([0.40, 0.35, 1.00, 1.00])
    done = col([1, 0, 1, 0])
    t, v = hp_lost_next_turn(turn, hp, done)
    assert v[0, 0]
    np.testing.assert_allclose(t[0, 0], 0.05, atol=1e-6)


def test_win_outcome_backfills_whole_segment():
    done = col([1, 0, 0, 1, 0])          # ep A = steps 0-2, ep B = 3-4 (open)
    succ = col([0, 0, 0, 1, 0])          # the done at 3 closed ep A as a WIN
    t, v = win_outcome(done, succ)
    assert v[0, 0] and v[1, 0] and v[2, 0]
    assert t[0, 0] == t[1, 0] == t[2, 0] == 1.0
    assert not v[3, 0] and not v[4, 0]   # ep B never closes in-buffer


def test_win_outcome_loss_label():
    done = col([1, 0, 1])
    succ = col([0, 0, 0])                # ep closed as a loss
    t, v = win_outcome(done, succ)
    assert v[0, 0] and v[1, 0] and t[0, 0] == 0.0
