"""v24: `run.ascension` obs float (schema 13) + per-episode ascension
sampling (`ascension_sample` / --ascension-random). The float is the
LAST run-block float segment; value = ascension/10. Sampling re-rolls
at reset() BEFORE run construction so map gen and the obs agree."""
import numpy as np
import pytest

from sts2_rl.run_env import STS2RunEnv, run_obs_segments_f, run_obs_layout


def _seg_names(segs):
    return [name for name, _ in segs]


def test_segment_is_last_run_block_float():
    names = _seg_names(run_obs_segments_f())
    assert names[-1] == "run.ascension"
    assert dict(run_obs_segments_f())["run.ascension"] == 1


def _ascension_slot():
    """Offset of run.ascension in the full f vector via the layout."""
    layout = run_obs_layout()
    off = 0
    for name, width in layout.f_segments:
        if name == "run.ascension":
            return off
        off += width
    raise AssertionError("run.ascension not in layout")


def test_obs_value_is_ascension_over_ten():
    env = STS2RunEnv(ascension=10)
    obs, _ = env.reset(seed=0)
    assert obs["f"][_ascension_slot()] == pytest.approx(1.0)
    env0 = STS2RunEnv(ascension=0)
    obs0, _ = env0.reset(seed=0)
    assert obs0["f"][_ascension_slot()] == pytest.approx(0.0)


def test_sampling_rerolls_per_reset_and_is_seeded():
    env = STS2RunEnv(ascension_sample=(0, 10))
    seen = set()
    for i in range(12):
        env.reset(seed=100 + i)
        seen.add(env._ascension)
        assert 0 <= env._ascension <= 10
    assert len(seen) > 1   # 12 seeded resets over 11 levels: >1 w.p. ~1


def test_sampled_value_reaches_obs_and_run():
    env = STS2RunEnv(ascension_sample=(7, 7))   # degenerate range = 7
    obs, _ = env.reset(seed=0)
    assert env._ascension == 7
    assert env._run.ascension == 7
    assert obs["f"][_ascension_slot()] == pytest.approx(0.7)


def test_default_is_fixed_ascension():
    env = STS2RunEnv(ascension=10)
    for i in range(3):
        env.reset(seed=i)
        assert env._ascension == 10


def test_spec_passthrough():
    from sts2_rl.vec_env import EnvSpec, build_env
    env = build_env(EnvSpec(kind="run", ascension_sample=(0, 10)))
    assert env._ascension_sample == (0, 10)
    dflt = build_env(EnvSpec(kind="run"))
    assert dflt._ascension_sample is None
