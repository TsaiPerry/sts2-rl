"""Shared pytest fixtures for the sts2_rl test suite.

T5b fix pass (review item 1): ``sts2_rl.obs._WARNED_SEGMENTS`` is a
process-global "warn once per segment name" latch (OBS_SCHEMA.md Sec.2.3),
which is the right production behaviour (a hot loop must not spam the log)
but makes any test using ``pytest.warns`` on an overflow warning
order-dependent: whichever test overflows a given segment name FIRST in the
process consumes the latch, and every later test on that same segment name
silently sees no warning, regardless of subset/order/xdist/pytest-randomly.

This is the third time process-global state has produced an
order-dependent test in this project (wave 1's ``__subclasses__()`` test
double, wave 3b's own overflow test, and now this one). Patching the one
failing call site would leave the trap armed for the next lane, so this
fixture fixes the CLASS of bug instead: reset the latch before every test
runs, so no test can inherit or steal another test's warning.
"""
from __future__ import annotations

import pytest

from sts2_rl.obs import reset_warned_segments
from sts2_rl.run_env import DECK_OVERFLOW_LOG_ENV, reset_deck_overflow_latch


@pytest.fixture(autouse=True)
def _reset_obs_warned_segments_latch():
    reset_warned_segments()
    yield


@pytest.fixture(autouse=True)
def _deck_overflow_log_to_tmp(tmp_path, monkeypatch):
    """Same class of trap as the warning latch, plus a side effect: the
    deck-overflow dump is process-latched AND writes a file, so without this
    the first overflowing test would both steal the dump from every later
    test and drop ``deck_overflow.log`` in the repo root."""
    reset_deck_overflow_latch()
    monkeypatch.setenv(DECK_OVERFLOW_LOG_ENV, str(tmp_path / "deck_overflow.log"))
    yield
    reset_deck_overflow_latch()
