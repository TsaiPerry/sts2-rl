"""v10 aux-head targets (spec 2026-08-13-aux-hp-head-gae-lambda-design):
hp-lost-over-next-3-floors labels from rollout obs columns."""
import numpy as np

from sts2_rl.aux_targets import hp_lost_next_floors


def _cols(floors, hp, done):
    f = (np.array(floors, dtype=np.float32) / 50.0)[:, None]
    h = np.array(hp, dtype=np.float32)[:, None]
    d = np.array(done, dtype=np.float32)[:, None]
    return f, h, d


def test_horizon_reached_sums_only_drops():
    # floors 0..4; hp 1.0 .9 .95 .7 .6 -> drops .1, 0 (heal), .25, .1
    f, h, d = _cols([0, 1, 2, 3, 4], [1.0, .9, .95, .7, .6], [0, 0, 0, 0, 0])
    t, v = hp_lost_next_floors(f, h, d)
    assert v[0, 0] and abs(t[0, 0] - 0.35) < 1e-6   # stop at floor>=3
    assert v[1, 0] and abs(t[1, 0] - 0.35) < 1e-6   # stop at floor>=4


def test_window_end_invalidates():
    f, h, d = _cols([0, 0, 1, 1, 2], [1.0] * 5, [0] * 5)
    t, v = hp_lost_next_floors(f, h, d)
    assert not v.any()   # never advances 3 floors, no episode end in window


def test_episode_end_is_a_valid_stop_and_no_leak():
    # done at index 3: obs 3 is a NEW episode (fresh hp, low floor)
    f, h, d = _cols([10, 10, 11, 0, 3], [0.5, 0.4, 0.4, 1.0, 0.2], [0, 0, 0, 1, 0])
    t, v = hp_lost_next_floors(f, h, d)
    assert v[0, 0] and abs(t[0, 0] - 0.1) < 1e-6    # closed episode: lost-until-end
    assert v[3, 0] and abs(t[3, 0] - 0.8) < 1e-6    # new episode reaches +3 at idx 4
    assert not v[4, 0]                              # open tail, horizon unreached


def test_tail_open_segment_invalid():
    f, h, d = _cols([0, 1, 1, 2, 2], [1.0, .9, .8, .7, .6], [0] * 5)
    t, v = hp_lost_next_floors(f, h, d)
    assert not v[4, 0]
